# الكود الكامل — المرحلة 11 (الاختبار الشامل والإصلاحات)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الكبيرة التي تغيّر منها جزء محدود تُعرض كمقتطف موسوم بوضوح («مُحدَّث — مقتطف») وفيه الدوال المتغيرة **كاملة**؛ وما عداها كامل. الملفات غير المذكورة لم تتغيّر عن المرحلة 10.

## الفهرس

- `services/order_service.py` — 132 سطراً (مُحدَّث (مقتطف): OrderService.create_order)
- `services/payment_service.py` — 240 سطراً (مُحدَّث (مقتطف): PaymentService._ensure_reference_unused, PaymentService._check_pending_limit, PaymentService.create_payment, PaymentService.create_method)
- `services/user_service.py` — 60 سطراً (مُحدَّث (مقتطف): UserService.get_or_create)
- `services/ticket_service.py` — 108 سطراً (مُحدَّث (مقتطف): TicketService.create_ticket, TicketService._ensure_no_open_ticket, TicketService._check_daily_limit, TicketService._validate_related_order)
- `services/broadcast_service.py` — 77 سطراً (مُحدَّث (مقتطف): BroadcastService.__init__, BroadcastService.send_batch, BroadcastService._send_batch_locked)
- `database/repositories/broadcasts.py` — 21 سطراً (مُحدَّث (مقتطف): BroadcastsRepository.claim_recipients)
- `services/wallet_service.py` — 60 سطراً (مُحدَّث (مقتطف): WalletService.adjust_balance)
- `services/provider_service.py` — 51 سطراً (مُحدَّث (مقتطف): ProviderService.create_provider)
- `utils/net_security.py` — 192 سطراً (مُحدَّث)
- `utils/datetime_utils.py` — 151 سطراً (مُحدَّث)
- `utils/logging_setup.py` — 110 سطراً (مُحدَّث)
- `core/exceptions.py` — 5 سطراً (مُحدَّث (مقتطف): SMMBotError.__init__)
- `database/database.py` — 3 سطراً (مُحدَّث (مقتطف): Tx.__init__)
- `handlers/admin/common.py` — 47 سطراً (مُحدَّث (مقتطف): admin_required)
- `handlers/common/guards.py` — 23 سطراً (مُحدَّث (مقتطف): guarded)
- `handlers/registry.py` — 41 سطراً (مُحدَّث (مقتطف): build_handlers)
- `core/constants.py` — 44 سطراً (مُحدَّث)
- `tests/e2e/test_concurrency_phase11.py` — 503 سطراً (جديد)
- `tests/e2e/test_ledger_fuzz_phase11.py` — 321 سطراً (جديد)
- `tests/e2e/test_scenarios_phase11.py` — 383 سطراً (جديد)
- `tests/e2e/test_dispatcher_phase11.py` — 331 سطراً (جديد)
- `tests/unit/test_code_quality_phase11.py` — 195 سطراً (جديد)
- `tests/integration/test_migrations.py` — 19 سطراً (مُحدَّث (مقتطف): test_failed_migration_rolls_back)

## `services/order_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

إعادة فحص `client_request_id` والحد اليومي والتكرار **داخل** المعاملة (TOCTOU).

```python
    async def create_order(
        self,
        user: User,
        *,
        service_id: int,
        link: str,
        quantity: str | int,
        client_request_id: str | None = None,
    ) -> Order:
        """
        إنشاء طلب جديد: تحقق كامل ← خصم الرصيد ← إنشاء الطلب ← إشعار — كلها معاملة واحدة.

        المدخلات:
            client_request_id : مفتاح المستخدم لمنع التكرار عند الضغط المزدوج.
                                إذا تكرر نفس المفتاح يُعاد الطلب الأول نفسه دون خصم جديد.

        المخرجات: الطلب بعد إنشائه (حالته `pending`).

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ServiceNotAvailableError               : الخدمة أو مزودها غير متاح.
            QuantityOutOfRangeError · InvalidLinkError · InvalidAmountError
            RateLimitedError                       : تجاوز الحد اليومي للطلبات.
            DuplicateOperationError                : طلب مطابق خلال نافذة التكرار.
            InsufficientBalanceError               : الرصيد لا يكفي (لا يُنشأ الطلب أصلاً).
        """
        await self.auth.guard(user)

        # 1) مفتاح منع التكرار: إن تكرر نفس المفتاح نُعيد الطلب الأصلي دون أي خصم جديد
        request_id = (client_request_id or f"u{user.id}:{new_token(8)}").strip()[:64]
        existing = await self.repos.orders.get_by_client_request_id(request_id)
        if existing is not None:
            logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s", existing.id, request_id)
            return existing

        # 2) الخدمة والمزود
        service = await self.catalog.get_available_service(service_id)
        provider = await self.repos.providers.get(service.provider_id)
        if provider is None:
            raise ServiceNotAvailableError(f"مزود الخدمة {service_id} غير موجود")
        health = await self.providers.health(provider)
        if not health.is_usable:
            raise ServiceNotAvailableError(
                f"المزود {provider.name} غير متاح: {health.reason}",
                user_message="❌ هذه الخدمة متوقفة مؤقتاً. جرّب لاحقاً.",
            )

        # 3) الرابط والكمية والتكلفة
        clean_link = validate_link(link, pattern=service.link_pattern)
        quote = await self.catalog.quote(service, quantity)

        symbol = await self.settings.money_symbol()
        min_order_units = await self.settings.get_money_units("min_order_amount_units", 0)
        if min_order_units and quote.cost_units < min_order_units:
            raise ValidationError(
                f"قيمة الطلب {quote.cost_units} أقل من الحد الأدنى {min_order_units}",
                user_message=(
                    "❌ الحد الأدنى لقيمة الطلب هو "
                    f"{format_units(min_order_units, symbol=symbol)}."
                ),
            )

        # 4) المعاملة الذرّية: فحوص الحدود ← إنشاء + خصم + سجل + إشعار
        async with self.db.transaction() as tx:
            # الفحوص الحاكمة داخل المعاملة نفسها: `BEGIN IMMEDIATE` يسلسل الكاتبين، فلا يمكن لنقرتين
            # متزامنتين أن تجتازا الفحص معاً ثم تُنشئا طلبين (ثغرة «افحص ثم نفّذ» التي كشفها اختبار التزامن)
            raced = await self.repos.orders.get_by_client_request_id(request_id)
            if raced is not None:
                logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s (سباق)", raced.id, request_id)
                return raced
            await self._check_daily_limit(user)
            await self._check_duplicate(user, service.id, clean_link, quote.quantity)

            order = await self.repos.orders.create(
                tx,
                user_id=user.id,
                service_id=service.id,
                provider_id=provider.id,
                service_name_snapshot=service.name,
                price_per_1000_snapshot_units=service.price_per_1000_units,
                link=clean_link,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                client_request_id=request_id,
                provider_cost_units=self._provider_cost(service, quote.quantity),
            )
            public_code = f"ORD-{order.id:06d}"
            await self.repos.orders.update_fields(tx, order.id, public_code=public_code)

            await self.wallet.charge_for_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                amount_units=quote.cost_units,
                description=f"طلب {service.name} × {quote.quantity}",
            )

            await self.repos.orders.add_history(
                tx,
                order_id=order.id,
                from_status=None,
                to_status=OrderStatus.PENDING,
                actor_type=ActorType.USER,
                actor_id=user.id,
                reason="إنشاء الطلب",
            )

            title, message = templates.order_created(
                code=public_code,
                service_name=service.name,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                event=NotificationType.ORDER_CREATED,
                title=title,
                message=message,
                payload={"order_id": order.id, "cost_units": quote.cost_units},
            )

        created = await self.repos.orders.get(order.id)
        if created is None:  # لا يحدث عملياً، لكن لا نُرجع قيمة غير مؤكدة أبداً
            raise OrderError(f"تعذر قراءة الطلب {order.id} بعد إنشائه")
        logger.info(
            "أنشأ المستخدم %s الطلب %s (%s × %s) بتكلفة %s",
            user.id, created.id, service.name, quote.quantity, quote.cost_units,
        )
        return created
```

## `services/payment_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

مرجع الحوالة والحد المعلّق وكود الطريقة تُفحص داخل المعاملة؛ الفحص الأول خارجها للرد السريع فقط.

```python
    async def _ensure_reference_unused(self, reference: str | None) -> None:
        """
        التأكد أن رقم الحوالة لم يُستخدم في طلب شحن معلّق أو معتمد (R5: إثبات مكرر).

        تُستدعى مرتين عمداً: قبل المعاملة (ردّ سريع) وداخلها (الفحص الحاكم تحت قفل الكتابة).

        الاستثناءات: DuplicateOperationError إن وُجد طلب سابق بنفس الرقم.
        """
        if not reference:
            return
        duplicate = await self.repos.payments.find_duplicate_reference(reference)
        if duplicate is not None:
            raise DuplicateOperationError(
                f"رقم الحوالة {reference} مستخدم في الطلب {duplicate.id}",
                user_message=(
                    "⚠️ رقم العملية هذا مُستخدم في طلب شحن سابق. "
                    "تواصل مع الدعم إن كان هناك خطأ."
                ),
            )
```

```python
    async def _check_pending_limit(self, user: User) -> None:
        """
        منع تكديس طلبات شحن معلّقة من نفس المستخدم.

        الاستثناءات: ValidationError عند تجاوز العدد المسموح.
        """
        max_pending = await self.settings.get_int("max_pending_payments_per_user", 3)
        if max_pending <= 0:
            return
        pending = await self.repos.payments.count_pending_by_user(user.id)
        if pending >= max_pending:
            raise ValidationError(
                f"المستخدم {user.id} لديه {pending} طلب شحن معلّق",
                user_message=(
                    f"⏳ لديك {pending} طلب شحن بانتظار المراجعة. "
                    "انتظر مراجعتها قبل إرسال طلب جديد."
                ),
            )
```

```python
    async def create_payment(
        self,
        user: User,
        *,
        method_id: int,
        raw_amount: str | int,
        transaction_reference: str | None = None,
        proof_file_id: str | None = None,
        proof_file_type: str | None = None,
        user_note: str | None = None,
    ) -> Payment:
        """
        إنشاء طلب شحن جديد بحالة «بانتظار المراجعة».

        المخرجات: طلب الشحن بعد إنشائه.

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ValidationError                        : طريقة متوقفة · إثبات ناقص · تجاوز عدد الطلبات المعلّقة.
            InvalidAmountError                     : مبلغ غير صالح أو خارج الحدود.
            DuplicateOperationError                : رقم الحوالة مستخدم في طلب سابق.
        """
        await self.auth.guard(user)
        method = await self.get_method(method_id)

        amount_units = parse_amount_units(raw_amount)
        min_units, max_units = await self.method_limits(method)
        validate_amount_range(
            amount_units, min_units=min_units, max_units=max_units, label="مبلغ الشحن"
        )

        reference = validate_transaction_reference(
            transaction_reference, required=bool(method.requires_proof)
        )
        if method.requires_proof and not proof_file_id and not reference:
            raise ValidationError(
                "إثبات الدفع مطلوب",
                user_message="❌ أرسل صورة إيصال التحويل أو رقم العملية.",
            )

        # فحص مبكر للرد السريع؛ الفحص الحاكم يُعاد داخل المعاملة أدناه (يمنع سباق التسجيلين المتزامنين)
        await self._ensure_reference_unused(reference)

        # رسوم الطريقة تُحسب الآن وتُخزَّن كلقطة داخل الطلب (لا تتأثر بتغيّرها لاحقاً)
        fee_units, net_units = self.fee_for(method, amount_units)
        if net_units <= 0:
            raise ValidationError(
                f"رسوم الطريقة {method.code} تبتلع كامل المبلغ {amount_units}",
                user_message=(
                    "❌ المبلغ أصغر من رسوم هذه الطريقة ولن يُضاف لك أي رصيد. "
                    "ارفع المبلغ أو اختر طريقة أخرى."
                ),
            )

        note = (
            clean_text(user_note, field="الملاحظة", max_length=MAX_USER_NOTE, min_length=0)
            if user_note
            else None
        )
        expiry_hours = await self.settings.get_int("payment_expiry_hours", 48)
        symbol = await self.settings.money_symbol()

        async with self.db.transaction() as tx:
            await self._ensure_reference_unused(reference)
            await self._check_pending_limit(user)
            payment = await self.repos.payments.create(
                tx,
                user_id=user.id,
                method_id=method.id,
                amount_units=amount_units,
                transaction_reference=reference,
                proof_file_id=proof_file_id,
                proof_file_type=proof_file_type,
                user_note=note,
                expires_at=iso_plus_seconds(expiry_hours * 3600) if expiry_hours > 0 else None,
                fee_units=fee_units,
            )

            title, message = templates.payment_received(
                payment_id=payment.id,
                amount_units=amount_units,
                symbol=symbol,
                fee_units=fee_units,
                net_units=net_units,
            )
            await self.notifications.notify_payment(
                tx,
                user_id=user.id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_RECEIVED,
                title=title,
                message=message,
            )

            admin_title, admin_message = templates.admin_new_payment(
                payment_id=payment.id,
                amount_units=amount_units,
                user_label=user.display_name,
                symbol=symbol,
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PAYMENTS_APPROVE,
                token=f"payment:{payment.id}:new",
                title=admin_title,
                message=admin_message,
            )

        logger.info(
            "طلب شحن جديد #%s من المستخدم %s بمبلغ %s عبر %s",
            payment.id, user.id, amount_units, method.code,
        )
        return payment
```

```python
    async def create_method(
        self,
        actor: User,
        *,
        code: str | None = None,
        name_ar: str,
        instructions_ar: str = "",
        account_details: str = "",
        type: str = "manual",
        min_amount_units: int = 0,
        max_amount_units: int | None = None,
        requires_proof: bool = True,
        sort_order: int | None = None,
        fee_percent_bp: int = 0,
        fee_fixed_units: int = 0,
    ) -> PaymentMethod:
        """
        إضافة طريقة شحن جديدة (صلاحية `payments.methods`).

        المدخلات:
            code           : كود داخلي؛ يُشتق تلقائياً من الاسم إن لم يُمرَّر.
            sort_order     : ترتيب العرض؛ الافتراضي آخر القائمة.
            fee_percent_bp : رسوم نسبية بنقاط الأساس (250 = 2.5%).

        الاستثناءات:
            PermissionDeniedError · ValidationError (كود مكرر أو بيانات غير صالحة)
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        clean_name = clean_text(name_ar, field="اسم الطريقة", max_length=64)
        if code:
            clean_code = (
                clean_text(code, field="كود الطريقة", max_length=32).lower().replace(" ", "_")
            )
        else:
            clean_code = await self.suggest_method_code(clean_name)

        if await self.repos.payment_methods.get_by_code(clean_code) is not None:
            raise ValidationError(
                f"كود طريقة الدفع {clean_code} مستخدم",
                user_message="❌ يوجد طريقة شحن بنفس الكود.",
            )

        values = self._validated_method_fields(
            {
                "instructions_ar": instructions_ar,
                "account_details": account_details,
                "type": type,
                "min_amount_units": min_amount_units,
                "max_amount_units": max_amount_units,
                "fee_percent_bp": fee_percent_bp,
                "fee_fixed_units": fee_fixed_units,
            }
        )
        order = (
            int(sort_order)
            if sort_order is not None
            else await self.repos.payment_methods.next_sort_order()
        )

        async with self.db.transaction() as tx:
            # إعادة الفحص داخل المعاملة: الفحص الأول للرد السريع فقط، وهذا الحاكم عند التزامن
            if await tx.fetchval("SELECT 1 FROM payment_methods WHERE code = ?", (clean_code,)):
                raise ValidationError(
                    f"كود طريقة الدفع {clean_code} مستخدم",
                    user_message="❌ يوجد طريقة شحن بنفس الكود.",
                )
            method = await self.repos.payment_methods.create(
                tx,
                code=clean_code,
                name_ar=clean_name,
                instructions_ar=values["instructions_ar"],
                account_details=values["account_details"],
                type=values["type"],
                min_amount_units=values["min_amount_units"],
                max_amount_units=values["max_amount_units"],
                requires_proof=requires_proof,
                sort_order=order,
                fee_percent_bp=values["fee_percent_bp"],
                fee_fixed_units=values["fee_fixed_units"],
            )
            await self.audit.log(
                tx,
                action="payments.methods",
                admin_id=actor.id,
                target_type="payment_method",
                target_id=method.id,
                after={"code": clean_code, "name_ar": clean_name, "action": "create"},
            )
        logger.info("أضاف الأدمن %s طريقة شحن %s", actor.id, clean_code)
        return method
```

## `services/user_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

/start المتزامنة تُرجع الحساب نفسه بدل `IntegrityError`.

```python
    async def get_or_create(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referrer_telegram_id: int | None = None,
    ) -> tuple[User, bool]:
        """
        جلب المستخدم أو إنشاؤه عند أول تفاعل مع البوت.

        المخرجات: (المستخدم، هل أُنشئ الآن؟)

        الاستثناءات:
            ValidationError : التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد.
        """
        existing = await self.repos.users.get_by_telegram_id(telegram_id)
        clean_username = normalize_username(username)

        if existing is not None:
            await self._refresh_profile(existing, clean_username, first_name, last_name)
            return (await self.repos.users.get_by_telegram_id(telegram_id) or existing), False

        if not await self.settings.registration_enabled():
            raise ValidationError(
                "التسجيل مغلق حالياً",
                user_message="🚧 التسجيل متوقف مؤقتاً. حاول لاحقاً أو تواصل مع الدعم.",
            )

        referrer_id: int | None = None
        if referrer_telegram_id and referrer_telegram_id != telegram_id:
            referrer = await self.repos.users.get_by_telegram_id(referrer_telegram_id)
            referrer_id = referrer.id if referrer else None

        async with self.db.transaction() as tx:
            # إعادة الفحص تحت قفل الكتابة: /start متزامنة من مستخدم جديد تصل هنا معاً،
            # فيُنشئ الأولُ الحساب ويستلم الباقون الحساب نفسه بدل `IntegrityError`
            raced = await self.repos.users.get_by_telegram_id(telegram_id)
            if raced is not None:
                return raced, False
            created = await self.repos.users.create(
                tx,
                telegram_id=telegram_id,
                username=clean_username,
                first_name=first_name,
                last_name=last_name,
                referrer_id=referrer_id,
            )
            await self.audit.log(
                tx,
                action="users.register",
                admin_id=None,
                target_type="user",
                target_id=created.id,
                details={"telegram_id": telegram_id, "referrer_id": referrer_id},
                source="bot",
            )
        logger.info("تسجيل مستخدم جديد %s (تيليجرام %s)", created.id, telegram_id)
        return created, True
```

## `services/ticket_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

تذكرة مفتوحة واحدة والحد اليومي داخل المعاملة؛ التحقق من الطلب المرتبط قبلها.

```python
    async def create_ticket(
        self,
        user: User,
        *,
        subject: str,
        message: str,
        category: str = "other",
        related_order_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportTicket:
        """
        فتح تذكرة دعم جديدة مع أول رسالة فيها.

        المخرجات: التذكرة بعد إنشائها.

        الاستثناءات:
            UserBannedError · MaintenanceModeError
            ValidationError : موضوع/نص غير صالح، تصنيف غير معروف، أو تجاوز الحد اليومي.
            TicketError     : لدى المستخدم تذكرة مفتوحة بالفعل.
        """
        await self.auth.guard(user)

        if category not in TICKET_CATEGORIES:
            raise ValidationError(
                f"تصنيف تذكرة غير معروف: {category}",
                user_message="❌ اختر تصنيفاً صحيحاً للتذكرة.",
            )
        clean_subject = validate_subject(subject)
        clean_message = validate_message(message)

        order_id = await self._validate_related_order(user, related_order_id)

        async with self.db.transaction() as tx:
            # الفحوص الحاكمة داخل المعاملة (تحت قفل الكتابة) حتى لا تُفتح تذكرتان بنقرتين متزامنتين
            await self._ensure_no_open_ticket(user)
            await self._check_daily_limit(user)
            ticket = await self.repos.tickets.create(
                tx,
                user_id=user.id,
                subject=clean_subject,
                category=category,
                related_order_id=order_id,
            )
            await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            title, admin_message = templates.admin_new_ticket(
                ticket_id=ticket.id, subject=clean_subject, user_label=user.display_name
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.TICKETS_VIEW,
                token=f"ticket:{ticket.id}:new",
                title=title,
                message=admin_message,
            )

        logger.info("فتح المستخدم %s التذكرة #%s (%s)", user.id, ticket.id, category)
        return ticket
```

```python
    async def _ensure_no_open_ticket(self, user: User) -> None:
        """
        التأكد أن المستخدم لا يملك تذكرة مفتوحة (قاعدة: تذكرة مفتوحة واحدة لكل مستخدم).

        الاستثناءات: TicketError إن وُجدت تذكرة مفتوحة.
        """
        if await self.repos.tickets.has_open_ticket(user.id):
            raise TicketError(
                f"المستخدم {user.id} لديه تذكرة مفتوحة",
                user_message="📬 لديك تذكرة مفتوحة بالفعل — تابع محادثتك فيها بدل فتح تذكرة جديدة.",
            )
```

```python
    async def _check_daily_limit(self, user: User) -> None:
        """
        تطبيق الحد اليومي لعدد التذاكر لكل مستخدم.

        الاستثناءات: ValidationError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_tickets_per_day", 5)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today = await self.repos.tickets.count_today_by_user(user.id, start_today)
        if today >= max_per_day:
            raise ValidationError(
                f"المستخدم {user.id} تجاوز {max_per_day} تذاكر اليوم",
                user_message=f"⏳ وصلت للحد اليومي ({max_per_day} تذاكر). حاول غداً.",
            )
```

```python
    async def _validate_related_order(self, user: User, order_id: int | None) -> int | None:
        """
        التأكد من أن الطلب المرتبط بالتذكرة يخص المستخدم نفسه.

        الاستثناءات: TicketError إذا كان الطلب لمستخدم آخر أو غير موجود.
        """
        if order_id is None:
            return None
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise TicketError(
                f"الطلب {order_id} لا يخص المستخدم {user.id}",
                user_message="❌ رقم الطلب المرتبط غير صحيح.",
            )
        return order.id
```

## `services/broadcast_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

قفل جولة الإرسال: جولة واحدة فقط في أي لحظة (تتخطّى الجولة الثانية ولا تنتظر).

```python
    def __init__(
        self,
        db: Database,
        repos: Repositories,
        auth: AuthService,
        audit: AuditService,
        notifications: NotificationService,
        settings: SettingsService,
    ) -> None:
        """تهيئة الخدمة باعتمادياتها."""
        self.db = db
        self.repos = repos
        self.auth = auth
        self.audit = audit
        self.notifications = notifications
        self.settings = settings
        #: قفل جولة الإرسال: يمنع عاملين متزامنين من حجز المستلمين أنفسهم وإرسال الرسالة مرتين
        #: (التسجيل يتم بعد الإرسال الفعلي، فلا يكفي شرط `status = 'pending'` وحده). صحيح لأن
        #: البوت عملية واحدة بقفل `bot.lock`؛ ولو انقطع التشغيل بين الإرسال والتسجيل يُعاد إرسال رسالة واحدة فقط.
        self._round_lock = asyncio.Lock()
```

```python
    async def send_batch(self, sender: BroadcastSender, *, limit: int | None = None) -> BroadcastRound:
        """
        جولة إرسال واحدة للإذاعة الجارية الحالية.

        المدخلات:
            sender : دالة إرسال من طبقة تيليجرام ترفع استثناءات الإشعارات المعروفة.
            limit  : حجم الدفعة (الافتراضي من الإعدادات `broadcast_batch_size`).

        المخرجات: حصيلة الجولة. إذاعة بلا متبقٍ تُغلق تلقائياً ويُشعَر منشئها.

        ملاحظة: كل مستلم يُسجَّل في معاملة قصيرة مستقلة، فلا تبقى قاعدة البيانات
        مقفلة أثناء انتظار الشبكة، ولا نفقد نتيجة من أُرسل له عند أي انقطاع.
        """
        if self._round_lock.locked():
            return BroadcastRound()          # جولة أخرى جارية الآن: لا ننتظرها ولا نزاحمها
        async with self._round_lock:
            return await self._send_batch_locked(sender, limit=limit)
```

```python
    async def _send_batch_locked(self, sender: BroadcastSender, *, limit: int | None) -> BroadcastRound:
        """جسم جولة الإرسال (يُستدعى حصراً تحت `_round_lock`)."""
        broadcast = await self.next_running()
        if broadcast is None:
            return BroadcastRound()

        batch_size = limit or await self.settings.get_int("broadcast_batch_size", 20)
        batch_size = max(1, min(50, batch_size))

        async with self.db.transaction() as tx:
            claimed = await self.repos.broadcasts.claim_recipients(
                tx, broadcast.id, limit=batch_size
            )

        round_report = BroadcastRound(broadcast_id=broadcast.id, claimed=len(claimed))
        for row in claimed:
            status, error = await self._send_one(sender, broadcast, int(row["telegram_id"]))
            async with self.db.transaction() as tx:
                recorded = await self.repos.broadcasts.mark_recipient(
                    tx, int(row["id"]), status=status, error=error
                )
                if recorded and status == RecipientStatus.BLOCKED:
                    await self.repos.users.set_blocked_bot(tx, int(row["user_id"]), True)
            if not recorded:
                continue  # سُجِّلت نتيجته في جولة أخرى — لا نعدّه مرتين
            if status == RecipientStatus.SENT:
                round_report.sent += 1
            elif status == RecipientStatus.BLOCKED:
                round_report.blocked += 1
            else:
                round_report.failed += 1

        remaining = await self.repos.broadcasts.pending_count(broadcast.id)
        if remaining == 0:
            await self._complete(broadcast.id)
            round_report.completed = True

        if round_report.claimed:
            logger.info("جولة إذاعة: %s", round_report.as_dict())
        return round_report
```

## `database/repositories/broadcasts.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

توثيق دقيق: لا حجز في القاعدة؛ منع التكرار عبر قفل الخدمة (at-least-once).

```python
    async def claim_recipients(self, tx: Tx, broadcast_id: int, *, limit: int = 20) -> list[dict]:
        """
        حجز دفعة من المستلمين المنتظرين للإرسال إليهم.

        الآلية: تحديث الحالة إلى sent يتم بعد الإرسال الفعلي؛ هنا نقرأ فقط دفعة صغيرة
        مرتبة (لا حجز فعلياً في القاعدة). منع الإرسال المزدوج بين جولتين متزامنتين
        مسؤولية `BroadcastService` عبر قفل الجولة (`_round_lock`)، أما التسجيل المشروط
        بـ pending في `mark_recipient` فيمنع العدّ المزدوج فقط. الضمان: at-least-once —
        انهيار العملية بين الإرسال والتسجيل قد يعيد إرسال رسالة واحدة لمستلم واحد.
        """
        rows = await tx.fetchall(
            """
            SELECT r.id, r.user_id, u.telegram_id
              FROM broadcast_recipients r
              JOIN users u ON u.id = r.user_id
             WHERE r.broadcast_id = ? AND r.status = 'pending'
             ORDER BY r.id LIMIT ?
            """,
            (broadcast_id, limit),
        )
        return [dict(row) for row in rows]
```

## `services/wallet_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

فرض الصلاحية `users.balance.credit/debit` داخل الخدمة نفسها (دفاع في العمق) — يتطلب `from core.permissions import Permission` في أعلى الملف.

```python
    async def adjust_balance(
        self, *, target: User, amount_units: int, admin: User, reason: str, credit: bool, token: str | None = None
    ) -> Transaction:
        """
        واجهة عالية المستوى للوحة الأدمن: تفتح معاملتها بنفسها وتُرجع الحركة.

        حواجز المرحلة 9: لا تسوية على حساب المنفِّذ نفسه، وسقف للعملية الواحدة
        ولليوم لغير الأدمن الأعلى (تُسجَّل محاولات التجاوز كأحداث أمنية).

        الاستثناءات: InvalidAmountError · InsufficientBalanceError · DuplicateOperationError
                     · PermissionDeniedError (إجراء ذاتي)
        """
        self._validate_amount(amount_units)
        if self.auth is not None:
            # دفاع في العمق: الصلاحية تُفرض في الخدمة نفسها لا في المعالج وحده (المرحلة 11)
            await self.auth.require_permission(
                admin,
                Permission.USERS_BALANCE_CREDIT if credit else Permission.USERS_BALANCE_DEBIT,
                context=f"wallet.adjust:user:{target.id}",
            )
            await self.auth.ensure_not_self_dealing(
                admin, target.id, what="تعديل رصيدك", context="wallet.adjust"
            )
        try:
            async with self.db.transaction() as tx:
                await self._enforce_adjust_caps(tx, admin, amount_units)
                if credit:
                    transaction = await self.manual_credit(
                        tx, user_id=target.id, amount_units=amount_units,
                        admin_id=admin.id, reason=reason, token=token,
                    )
                else:
                    transaction = await self.manual_debit(
                        tx, user_id=target.id, amount_units=amount_units,
                        admin_id=admin.id, reason=reason, token=token,
                    )
                await self.repos.audit.log(
                    tx,
                    action="users.balance.credit" if credit else "users.balance.debit",
                    admin_id=admin.id,
                    target_type="user",
                    target_id=target.id,
                    before={"balance_units": transaction.balance_before_units},
                    after={"balance_units": transaction.balance_after_units},
                    details={"reason": reason, "amount_units": amount_units},
                )
        except _AdjustCapExceeded as exc:
            # التسجيل خارج المعاملة الملغاة حتى لا يضيع الأثر مع التراجع
            if self.auth is not None:
                await self.auth.audit.log_security_event(
                    event=exc.event,
                    user_id=admin.id,
                    target_type="user",
                    target_id=target.id,
                    details=exc.details,
                )
            raise InvalidAmountError(
                f"{exc.event}: {exc.details}", user_message=exc.user_message
            ) from exc
        return transaction
```

## `services/provider_service.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

فحص تكرار الاسم داخل المعاملة وخطأ عربي بدل `IntegrityError`.

```python
    async def create_provider(
        self,
        actor: User,
        *,
        name: str,
        api_url: str,
        api_key: str,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        timeout_seconds: int = 30,
    ) -> Provider:
        """
        إضافة مزود جديد مع تشفير مفتاحه قبل التخزين.

        الاستثناءات: PermissionDeniedError · ValidationError · EncryptionError
        """
        await self.auth.require_permission(actor, Permission.PROVIDERS_CREATE, context="provider.create")
        clean_name = clean_text(name, field="اسم المزود", max_length=60, min_length=2)
        clean_gateway = validate_public_https_url(api_url)   # https + مضيف عام (منع SSRF)
        key = (api_key or "").strip()
        if len(key) < 8:
            raise ProviderError(
                "مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح."
            )

        async with self.db.transaction() as tx:
            # الفحص داخل المعاملة نفسها (BEGIN IMMEDIATE) فلا يتسلل مكرر عند إنشاءين متزامنين
            if await tx.fetchval("SELECT 1 FROM providers WHERE name = ?", (clean_name,)):
                raise ProviderError(
                    f"اسم المزود {clean_name} مستخدم", user_message="❌ يوجد مزود بنفس الاسم."
                )
            provider = await self.repos.providers.create(
                tx,
                name=clean_name,
                api_url=clean_gateway,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
                api_type=api_type,
                currency=currency,
                timeout_seconds=timeout_seconds,
            )
            await self.audit.log(
                tx,
                action="providers.create",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider.id,
                after={"name": clean_name, "api_url": clean_gateway, "api_type": api_type},
            )
        logger.info("أضاف الأدمن %s المزود %s (%s)", actor.id, provider.id, clean_name)
        return provider
```

## `utils/net_security.py` (مُحدَّث)

```python
"""
حماية الاتصالات الخارجية: منع SSRF وتسريب مفاتيح المزودين (المرحلة 9).

المشكلة:
    رابط API للمزود يُدخله أدمن، والبوت يرسل إليه مفتاح المزود مع كل طلب.
    رابط خبيث أو خاطئ يعني أحد ثلاثة أخطار:
        1. **SSRF**: توجيه البوت إلى عنوان داخلي (127.0.0.1، 169.254.169.254،
           شبكة الخادم الخاصة) لقراءة خدمات لا يجوز الوصول إليها.
        2. **تسريب المفتاح**: رابط `http://` يرسل المفتاح نصاً صريحاً عبر الشبكة.
        3. **بيانات اعتماد داخل الرابط** (`https://user:pass@host`) تظهر في اللوقات.

الحل (طبقتان):
    • عند الحفظ: `validate_public_https_url` — فحص نصي سريع (بروتوكول، منفذ،
      اسم المضيف، عنوان IP حرفي).
    • عند الإرسال: `ensure_public_host` — يحلّ اسم النطاق ويرفض إن أشار إلى أي
      عنوان غير عام (يسدّ حيلة نطاق عام يشير إلى عنوان داخلي).

قيد معروف (موثَّق في تقرير المرحلة): بين فحص DNS وفتح الاتصال فجوة زمنية صغيرة
(DNS rebinding)؛ الحد منها كاملاً يتطلب تثبيت العنوان داخل الناقل، وهو خارج
نطاق هذه المرحلة. الفحص الحالي يسدّ الأخطاء الشائعة والهجمات المباشرة.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from core.exceptions import ProviderPermanentError, ValidationError

#: لواحق أسماء المضيفين المحلية/الداخلية المرفوضة دائماً
BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    ".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet", ".private",
)

#: أسماء مضيفين محجوزة مرفوضة بالنص
BLOCKED_HOSTNAMES: frozenset[str] = frozenset({"localhost", "ip6-localhost", "metadata.google.internal"})

#: المنافذ المسموحة لواجهات المزودين (غير ذلك يُرفض: لا فحص منافذ داخلية)
ALLOWED_PORTS: frozenset[int] = frozenset({443, 8443})

#: مدة بقاء نتيجة فحص DNS الناجحة (ثانية) — لتفادي حلّ الاسم عند كل طلب
DNS_CACHE_TTL_SECONDS: float = 300.0

#: نوع دالة حلّ الأسماء (قابلة للحقن في الاختبارات): اسم المضيف ← قائمة عناوين IP
Resolver = Callable[[str], Awaitable[list[str]]]

_dns_cache: dict[str, float] = {}


def is_public_ip(value: str) -> bool:
    """
    هل العنوان عام قابل للوصول من الإنترنت؟

    يرفض: الحلقة المحلية، الخاص (RFC1918/ULA)، link-local (169.254.x.x)،
    المحجوز، البث المتعدد، وغير المحدد (0.0.0.0). العناوين IPv4 المضمَّنة في
    IPv6 (`::ffff:127.0.0.1`) تُفحص بعد فك التضمين حتى لا تلتف على القاعدة.
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def _reject(reason: str, *, field: str) -> ValidationError:
    """بناء خطأ تحقق موحّد برسالة عربية تذكر سبب الرفض."""
    return ValidationError(
        f"{field} مرفوض: {reason}",
        user_message=f"❌ {field} غير آمن: {reason}",
    )


def validate_public_https_url(url: str | None, *, field: str = "رابط API") -> str:
    """
    فحص نصي لرابط مزود: https فقط، منفذ مسموح، مضيف عام، بلا بيانات اعتماد.

    المخرجات: الرابط بعد إزالة الفراغات.

    الاستثناءات:
        ValidationError : أي مخالفة مع ذكر سببها بالعربية.
    """
    text = (url or "").strip()
    if not text:
        raise _reject("الرابط فارغ", field=field)
    if len(text) > 300:
        raise _reject("الرابط طويل جداً", field=field)
    if any(ch.isspace() or ord(ch) < 32 for ch in text):
        raise _reject("الرابط يحتوي مسافات أو محارف تحكم", field=field)

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise _reject("صيغة الرابط غير صحيحة", field=field) from exc

    if parts.scheme.lower() != "https":
        raise _reject("يجب أن يبدأ بـ https:// (مفتاح المزود لا يُرسل بلا تشفير)", field=field)
    if parts.username or parts.password:
        raise _reject("لا يجوز وضع اسم مستخدم أو كلمة مرور داخل الرابط", field=field)

    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise _reject("لا يوجد اسم نطاق", field=field)
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise _reject("النطاق محلي/داخلي", field=field)

    is_literal_ip = _looks_like_ip(host)
    if is_literal_ip:
        if not is_public_ip(host):
            raise _reject("عنوان IP غير عام (داخلي أو محجوز)", field=field)
    elif "." not in host:
        raise _reject("اسم النطاق غير مكتمل", field=field)

    if port is not None and port not in ALLOWED_PORTS:
        raise _reject(f"المنفذ {port} غير مسموح (المسموح: 443 أو 8443)", field=field)
    return text


def _looks_like_ip(host: str) -> bool:
    """هل النص عنوان IP حرفي (v4 أو v6)؟ — الأرقام المجرّدة (مثل 2130706433) تُعدّ IP أيضاً."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # صيغ قديمة يقبلها بعض المحللات: 2130706433 أو 0x7f000001 أو 017700000001
        return _is_numeric_notation(host)
    return True


def _is_numeric_notation(host: str) -> bool:
    """هل النص عدد صحيح بصيغة عشرية/سداسية/ثمانية (عنوان IP مموَّه بصيغة رقمية)؟"""
    try:
        int(host, 0)
    except ValueError:
        return False
    return True


async def _system_resolver(host: str) -> list[str]:
    """حلّ اسم المضيف عبر نظام التشغيل دون حجب حلقة الأحداث."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


async def ensure_public_host(url: str, *, resolver: Resolver | None = None) -> None:
    """
    التأكد وقت الإرسال أن اسم مضيف الرابط يشير إلى عناوين عامة فقط.

    المدخلات:
        url      : رابط المزود (سبق تحقق صيغته عند الحفظ).
        resolver : دالة حلّ بديلة (للاختبارات).

    الاستثناءات:
        ProviderPermanentError : النطاق لا يُحلّ، أو أحد عناوينه غير عام.
                                 (دائم لأن إعادة المحاولة لن تغيّر الحكم الأمني.)
    """
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        raise ProviderPermanentError("رابط المزود بلا اسم مضيف")

    now = time.monotonic()
    cached_until = _dns_cache.get(host, 0.0)
    if cached_until > now:
        return

    if _looks_like_ip(host):
        addresses = [host]
    else:
        try:
            addresses = await (resolver or _system_resolver)(host)
        except OSError as exc:
            raise ProviderPermanentError(f"تعذّر حلّ نطاق المزود {host}: {type(exc).__name__}") from exc

    if not addresses:
        raise ProviderPermanentError(f"النطاق {host} لا يشير إلى أي عنوان")
    for address in addresses:
        if not is_public_ip(address):
            raise ProviderPermanentError(
                f"النطاق {host} يشير إلى عنوان غير عام ({address}) — تم رفض الاتصال حمايةً من SSRF"
            )
    _dns_cache[host] = now + DNS_CACHE_TTL_SECONDS


def clear_dns_cache() -> None:
    """تفريغ ذاكرة نتائج DNS (للاختبارات وعند تغيير رابط مزود)."""
    _dns_cache.clear()
```

## `utils/datetime_utils.py` (مُحدَّث)

```python
"""
أدوات الوقت — قاعدة ثابتة في المشروع:

    • كل ما يُخزَّن في قاعدة البيانات بتوقيت UTC وبصيغة ISO-8601 منتهية بحرف Z.
    • التحويل إلى التوقيت المحلي (Asia/Aden افتراضياً) يتم عند العرض فقط.

السبب: خلط التوقيتات يفسد الإحصائيات اليومية ويجعل مقارنة الأوقات غير موثوقة.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

ISO_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"

#: المنطقة الزمنية المعتمدة للعرض وللمهام اليومية (تُستخدم عند عدم تمرير غيرها)
DEFAULT_TIMEZONE: str = "Asia/Aden"

#: كائن المنطقة الزمنية الجاهز (يحتاجه `run_daily` في JobQueue)
APP_TIMEZONE: ZoneInfo = ZoneInfo(DEFAULT_TIMEZONE)


def utc_now() -> datetime:
    """الوقت الحالي بتوقيت UTC ككائن datetime واعٍ بالمنطقة الزمنية."""
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """تحويل datetime إلى نص ISO-8601 بتوقيت UTC (الصيغة المعتمدة للتخزين)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime(ISO_FORMAT)


def utc_now_iso() -> str:
    """الوقت الحالي جاهزاً للتخزين في قاعدة البيانات."""
    return to_iso(utc_now())


def parse_iso(value: str | None) -> datetime | None:
    """تحويل نص مخزَّن إلى datetime، وإرجاع None إذا كانت القيمة فارغة أو غير صالحة."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso_plus_seconds(seconds: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت مستقبلي بعد عدد من الثواني (يُستخدم للقفول ومواعيد الفحص)."""
    return to_iso((base or utc_now()) + timedelta(seconds=seconds))


def iso_minus_days(days: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت ماضٍ قبل عدد من الأيام (يُستخدم في التقارير والتنظيف)."""
    return to_iso((base or utc_now()) - timedelta(days=days))


def is_past(value: str | None) -> bool:
    """هل مرّ هذا الوقت المخزَّن؟ (تُعامل القيمة الفارغة على أنها منتهية)."""
    moment = parse_iso(value)
    return True if moment is None else moment <= utc_now()


def to_local_text(value: str | None, timezone: str = "Asia/Aden", fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    تحويل وقت مخزَّن (UTC) إلى نص بالتوقيت المحلي للعرض على المستخدم.

    المدخلات:
        value    : النص المخزَّن في قاعدة البيانات.
        timezone : المنطقة الزمنية للعرض.
        fmt      : صيغة العرض.

    المخرجات: نص منسّق، أو "-" إذا لم توجد قيمة.
    """
    moment = parse_iso(value)
    if moment is None:
        return "-"
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):  # منطقة زمنية غير معروفة — نعرض بتوقيت UTC بدل الانهيار
        zone = UTC
    return moment.astimezone(zone).strftime(fmt)


def day_bounds_utc(days_back: int = 0, timezone: str = "Asia/Aden") -> tuple[str, str]:
    """
    حدود يوم محلي كاملة معبَّراً عنها بتوقيت UTC (لاستعلامات الإحصائيات اليومية).

    المدخلات:
        days_back : 0 = اليوم، 1 = أمس ... إلخ.
        timezone  : المنطقة الزمنية المحلية المعتمدة للعرض.

    المخرجات: (بداية اليوم، نهاية اليوم) كنصين ISO بتوقيت UTC.
    """
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):   # اسم منطقة غير صالح ⇒ UTC
        zone = UTC
    local_now = utc_now().astimezone(zone) - timedelta(days=days_back)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return to_iso(start_local), to_iso(end_local)


def _zone(timezone: str) -> tzinfo:
    """كائن المنطقة الزمنية، وUTC إذا كان الاسم غير معروف (لا نفشل في التقارير بسبب إعداد)."""
    try:
        return ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):                # اسم منطقة غير صالح/ناقص tzdata
        return UTC


def local_range_utc(
    first_days_back: int, last_days_back: int = 0, timezone: str = DEFAULT_TIMEZONE
) -> tuple[str, str]:
    """
    مدى أيام محلية كاملة بتوقيت UTC: من بداية اليوم `first_days_back` حتى نهاية اليوم `last_days_back`.

    مثال: `(6, 0)` = آخر 7 أيام تقويمية شاملةً اليوم · `(1, 1)` = أمس وحده.
    الحساب بتاريخ المنطقة المحلية (لا بطرح 24 ساعة) فلا ينحرف مع تغيّر التوقيت الصيفي.
    """
    zone = _zone(timezone)
    today = utc_now().astimezone(zone).date()
    start_day = today - timedelta(days=first_days_back)
    end_day = today - timedelta(days=last_days_back) + timedelta(days=1)
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=zone)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=zone)
    return to_iso(start), to_iso(end)


def local_month_range_utc(timezone: str = DEFAULT_TIMEZONE) -> tuple[str, str]:
    """من بداية الشهر المحلي الحالي حتى نهاية اليوم المحلي (بتوقيت UTC)."""
    zone = _zone(timezone)
    today = utc_now().astimezone(zone).date()
    start = datetime(today.year, today.month, 1, tzinfo=zone)
    return to_iso(start), local_range_utc(0, 0, timezone)[1]


def local_day_of(value: str | None, timezone: str = DEFAULT_TIMEZONE) -> str | None:
    """تاريخ اليوم المحلي `YYYY-MM-DD` لوقت مخزَّن (None إذا كانت القيمة غير صالحة)."""
    moment = parse_iso(value)
    if moment is None:
        return None
    return moment.astimezone(_zone(timezone)).strftime("%Y-%m-%d")
```

## `utils/logging_setup.py` (مُحدَّث)

```python
"""
إعداد نظام التسجيل (Logging) المركزي.

الميزات:
    • ملف دوّار (RotatingFileHandler) حتى لا يتضخم حجم اللوق.
    • إخراج على الشاشة أثناء التطوير.
    • فلتر أمني يحذف أي توكن أو مفتاح API قبل الكتابة.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from utils.security import sanitize

_CONFIGURED: bool = False


class SecretRedactionFilter(logging.Filter):
    """فلتر يمنع كتابة الأسرار (التوكن/المفاتيح) داخل ملفات اللوق."""

    def filter(self, record: logging.LogRecord) -> bool:
        """تنقية نص الرسالة قبل إخراجها؛ يُرجع True دائماً لأننا لا نحذف السجلات."""
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError):  # فشل تنسيق الرسالة (args غير مطابقة) ⇒ نمرّر السجل كما هو
            return True
        cleaned = sanitize(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """
    منسّق يحذف الأسرار من **السطر النهائي كاملاً** بما فيه تتبّع الاستثناء.

    لماذا لا يكفي الفلتر وحده؟ الفلتر يرى `record.msg` فقط، أما `exc_info`
    فيُنسَّق لاحقاً داخل المنسّق — واستثناءات httpx/تيليجرام تحمل الرابط الكامل
    (وفيه التوكن) في نص الخطأ. التنقية هنا تسدّ هذه الثغرة.
    """

    def format(self, record: logging.LogRecord) -> str:
        """تنسيق السجل ثم تنقية الناتج النهائي من الأسرار."""
        return sanitize(super().format(record))


def setup_logging(
    log_file: Path | str = "logs/bot.log",
    level: str = "INFO",
    *,
    console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """
    تهيئة اللوق المركزي للمشروع (تُستدعى مرة واحدة عند الإقلاع).

    المدخلات:
        log_file     : مسار ملف اللوق.
        level        : مستوى التسجيل (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        console      : إظهار السجلات على الشاشة أيضاً.
        max_bytes    : الحجم الأقصى للملف قبل التدوير.
        backup_count : عدد الملفات المحفوظة بعد التدوير.

    المخرجات: اللوجر الجذري بعد التهيئة.
    """
    global _CONFIGURED

    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if _CONFIGURED:
        return root

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction = SecretRedactionFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redaction)
        root.addHandler(stream_handler)

    # تخفيف ضجيج المكتبات الخارجية
    for noisy in ("httpx", "httpcore", "aiosqlite", "telegram.vendor", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """الحصول على لوجر باسم الوحدة الحالية."""
    return logging.getLogger(name)
```

## `core/exceptions.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)



```python
    def __init__(self, message: str | None = None, *, user_message: str | None = None) -> None:
        """تخزين الرسالة التقنية (للسجل) والرسالة العربية المبسطة (للمستخدم)."""
        super().__init__(message or self.__class__.__doc__ or "")
        if user_message:
            self.user_message = user_message
```

## `database/database.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)



```python
    def __init__(self, conn: aiosqlite.Connection) -> None:
        """ربط المعاملة باتصال aiosqlite المفتوح."""
        self._conn = conn
```

## `handlers/admin/common.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

أُضيف docstring للدالة الداخلية `decorator`.

```python
def admin_required(permission: str | None = None) -> Callable[[_T], _T]:
    """
    مزخرف يمنع تنفيذ معالج الأدمن إلا لمن يملك الصلاحية فعلاً.

    المدخلات:
        permission : رمز الصلاحية المطلوبة للإجراء (None ⇐ يكفي دخول اللوحة).

    المخرجات:
        نفس المعالج مغلَّفاً؛ وعند الرفض يرد بتنبيه ويُرجع `ConversationHandler.END`
        (قيمة غير ضارة خارج المحادثات، وتُنهي المحادثة داخلها).
    """

    def decorator(func: _T) -> _T:
        """تغليف المعالج بفحص الصلاحية المطلوبة."""

        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """التحقق من الصلاحية قبل تمرير التحديث إلى الشاشة الفعلية."""
            services = services_of(context)
            user = require_user(context)
            try:
                await services.auth.require_permission(
                    user, Permission.ADMIN_ACCESS, context=func.__name__
                )
                if permission is not None and permission != Permission.ADMIN_ACCESS:
                    await services.auth.require_permission(
                        user, permission, context=func.__name__
                    )
            except PermissionDeniedError as exc:
                logger.warning(
                    "رفض وصول إداري: المستخدم %s ← %s (%s)",
                    user.telegram_id,
                    permission or Permission.ADMIN_ACCESS,
                    func.__name__,
                )
                await answer_callback(update, exc.user_message, alert=True)
                if update.callback_query is None:
                    await send(update, context, exc.user_message, back_panel_kb())
                clear_flow(context)
                return ConversationHandler.END
            return await func(update, context)

        #: تُقرأ في الاختبارات للتأكد أن كل معالج أدمن محميّ بصلاحية صحيحة
        wrapper.admin_permission = permission or Permission.ADMIN_ACCESS  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
```

## `handlers/common/guards.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

أُضيف docstring للدالة الداخلية `wrapper`.

```python
def guarded(func: _T) -> _T:
    """
    لفّ معالج واجهة لعرض أخطاء النظام المتوقعة برسالة عربية بدل تعطّل البوت.

    المخرجات: نفس المعالج مغلَّفاً (يحافظ على قيمة الإرجاع في المسار الناجح).
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنفيذ المعالج مع تحويل أخطاء النظام المعروفة إلى رسالة عربية للمستخدم."""
        try:
            return await func(update, context)
        except SMMBotError as exc:
            user = update.effective_user
            logger.info(
                "خطأ متوقع في %s للمستخدم %s: %s",
                func.__name__, user.id if user else "?", exc,
            )
            await answer_callback(update)
            await send(update, context, exc.user_message)
            return None

    return wrapper  # type: ignore[return-value]
```

## `handlers/registry.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

إعادة تسمية متغير الحلقة (كان يحجب دالة `conversation` المستوردة).

```python
def build_handlers(
    limiter: RateLimiter | None = None, guard: AbuseGuard | None = None
) -> list[tuple[int, BaseHandler]]:
    """
    بناء قائمة (المجموعة، المعالج) بالترتيب الصحيح.

    الترتيب داخل المجموعة 0:
        المحادثات ← الأوامر العامة ← أزرار الشاشات ← المسارات الاحتياطية.
    السبب: المحادثة النشطة يجب أن تلتقط /start و/cancel قبل المعالج العام،
    والمسار الاحتياطي يجب أن يكون الأخير حتى لا يبتلع أزراراً صحيحة.
    """
    handlers: list[tuple[int, BaseHandler]] = [
        (MIDDLEWARE_GROUP, TypeHandler(Update, UserContextMiddleware(limiter, guard)))
    ]

    for conversation_handler in conversation_handlers():
        handlers.append((MAIN_GROUP, conversation_handler))

    handlers.extend(
        [
            (MAIN_GROUP, CommandHandler("start", navigation.start_command)),
            (MAIN_GROUP, CommandHandler("help", navigation.help_command)),
            (MAIN_GROUP, CommandHandler("id", navigation.id_command)),
            (MAIN_GROUP, CommandHandler("cancel", fallbacks.cancel_command)),
        ]
    )

    for command in admin_command_handlers():
        handlers.append((MAIN_GROUP, command))

    for handler in screen_handlers():
        handlers.append((MAIN_GROUP, handler))

    handlers.extend(
        [
            (MAIN_GROUP, CallbackQueryHandler(fallbacks.unknown_callback)),
            (MAIN_GROUP, MessageHandler(filters.COMMAND, fallbacks.unknown_command)),
            (MAIN_GROUP, MessageHandler(filters.TEXT | filters.ATTACHMENT, fallbacks.free_text)),
        ]
    )
    return handlers
```

## `core/constants.py` (مُحدَّث)

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.12.0-phase11"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

## `tests/e2e/test_concurrency_phase11.py` (جديد)

```python
"""
المرحلة 11 — اختبارات التزامن (Race Conditions) على الخدمات الحقيقية.

لماذا هذه الاختبارات؟
    بقية الاختبارات تشغّل العمليات واحدة تلو الأخرى، بينما الواقع: ضغطتان متزامنتان على «اعتماد»،
    أو مهمتا إرسال تعملان معاً، أو عميل ينقر «تأكيد» عشر مرات. أي ثغرة هنا = **مال يتكرر أو يضيع**.

المنهج: `asyncio.gather` على عمليات متنافسة + قاعدة بيانات حقيقية، ثم فحص ثوابت لا يجوز كسرها:
    • لا رصيد سالب أبداً · • كل عملية مالية تحدث مرة واحدة فقط · • الدفتر يطابق الرصيد
    • الطلب لا يُرسل للمزود أكثر من مرة.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import OrderStatus, PaymentStatus, TransactionType
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer

pytestmark = pytest.mark.asyncio


async def _settle(results: list) -> tuple[list, list[BaseException]]:
    """فصل نتائج `gather(return_exceptions=True)` إلى ناجحة وفاشلة."""
    ok = [item for item in results if not isinstance(item, BaseException)]
    failed = [item for item in results if isinstance(item, BaseException)]
    return ok, failed


async def _fund(services: ServiceContainer, user: User, admin: User, units: int) -> None:
    """شحن رصيد عبر المحفظة المركزية (المسار الوحيد المسموح لتغيير الرصيد)."""
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=admin, reason="رصيد اختبار", credit=True)


async def _slow_provider(mock_client, delay: float = 0.01) -> None:
    """جعل إرسال المزود يتأخر فعلاً (يفرض تداخل المهام المتزامنة بدل تنفيذها تسلسلياً بالصدفة)."""
    original = mock_client.add_order

    async def slow(**kwargs):
        await asyncio.sleep(delay)
        return await original(**kwargs)

    mock_client.add_order = slow


# ======================================================================== #
#                               الطلبات والرصيد                              #
# ======================================================================== #


async def test_concurrent_orders_never_overdraw_balance(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """10 طلبات متزامنة والرصيد يكفي 3 فقط ⇒ ينجح 3 بالضبط ولا رصيد سالب ولا طلب بلا خصم."""
    await _fund(services, user, admin, 30_000)
    await services.settings.set("duplicate_order_window_minutes", 0)

    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link=f"https://instagram.com/race{i}", quantity=1000
            )
            for i in range(10)
        ],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)

    assert len(ok) == 3, f"نجح {len(ok)} طلباً والرصيد يكفي 3"
    assert len(failed) == 7
    assert await services.wallet.balance_units(user.id) == 0
    assert await repos.orders.count_by_user(user.id) == 3
    charges = [t for t in await repos.transactions.list_by_user(user.id, limit=50) if t.type == TransactionType.ORDER]
    assert len(charges) == 3
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_double_click_same_order_creates_one_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """نقرتان متزامنتان على «تأكيد» لنفس الطلب (نفس الرابط والكمية) ⇒ طلب واحد وخصم واحد."""
    await _fund(services, user, admin, 100_000)
    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link="https://instagram.com/p/same", quantity=1000
            )
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    assert len(ok) == 1, "حماية الطلب المكرر لم تصمد تحت التزامن"
    assert await repos.orders.count_by_user(user.id) == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_concurrent_submitters_send_each_order_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service, mock_client,
) -> None:
    """4 مهام إرسال متزامنة على 6 طلبات ⇒ كل طلب يُرسل للمزود مرة واحدة (لا طلب مزدوج = لا خسارة)."""
    await _fund(services, user, admin, 500_000)
    await services.settings.set("duplicate_order_window_minutes", 0)
    for i in range(6):
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/sub{i}", quantity=1000
        )
    await _slow_provider(mock_client)

    await asyncio.gather(*[services.orders.process_pending_orders(worker=f"w{i}", limit=3) for i in range(4)])
    await services.orders.process_pending_orders(limit=10)      # ما فات المهام الأولى

    adds = [call for call in mock_client.calls if call[0] == "add"]
    assert len(adds) == 6, f"أُرسل {len(adds)} استدعاء إنشاء لـ6 طلبات"
    links = [call[1].get("link") for call in adds]
    assert len(set(links)) == 6, "رابط أُرسل مرتين للمزود"
    statuses = {o.status for o in await repos.orders.list_by_user(user.id, limit=20)}
    assert statuses == {OrderStatus.SUBMITTED}


async def test_concurrent_cancel_refunds_exactly_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """إلغاء المستخدم + إلغاء الأدمن + تعليم الفشل في اللحظة نفسها ⇒ استرجاع واحد فقط."""
    await _fund(services, user, admin, 50_000)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/c", quantity=1000
    )
    assert await services.wallet.balance_units(user.id) == 40_000

    results = await asyncio.gather(
        services.orders.cancel_by_user(user, order.id),
        services.orders.cancel_by_user(user, order.id),
        services.orders.admin_cancel(admin, order.id, "اختبار تزامن"),
        services.orders.admin_mark_failed(admin, order.id, "اختبار تزامن"),
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    assert len(ok) >= 1
    assert await services.wallet.balance_units(user.id) == 50_000, "استرجاع مكرر أو ناقص"
    refunds = [t for t in await repos.transactions.list_by_user(user.id, limit=50) if t.type == TransactionType.REFUND]
    assert len(refunds) == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced
    final = await repos.orders.get(order.id)
    assert final is not None and final.refund_amount_units == 10_000


async def test_concurrent_due_checks_complete_order_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service, mock_client,
) -> None:
    """3 مهام متابعة متزامنة ⇒ الاكتمال والإشعار مرة واحدة."""
    await _fund(services, user, admin, 50_000)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/d", quantity=1000
    )
    await services.orders.process_pending_orders()
    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Completed", delivered=1000)
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, order.id, next_check_at="2000-01-01T00:00:00+00:00")

    await asyncio.gather(*[services.orders.process_due_orders(worker=f"c{i}") for i in range(3)])

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.COMPLETED
    completed_notes = [
        n for n in await repos.notifications.list_for_user(user.id) if n.type == "order_completed"
    ]
    assert len(completed_notes) == 1, "إشعار اكتمال مكرر"
    history = [row.to_status for row in await repos.orders.history(order.id)]
    assert history.count(OrderStatus.COMPLETED) == 1


# ======================================================================== #
#                                  المدفوعات                                 #
# ======================================================================== #


async def _pending_payment(services: ServiceContainer, user: User, method_id: int, ref: str = "TRX-RACE"):
    """إنشاء طلب شحن معلّق جاهز للمراجعة."""
    return await services.payments.create_payment(
        user, method_id=method_id, raw_amount="5", transaction_reference=ref,
        proof_file_id="proof", proof_file_type="photo",
    )


async def test_concurrent_approvals_credit_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, payment_method,
) -> None:
    """5 اعتمادات متزامنة (أدمنان) لنفس الدفعة ⇒ رصيد يُضاف مرة واحدة وحركة إيداع واحدة (R12)."""
    payment = await _pending_payment(services, user, payment_method.id)

    results = await asyncio.gather(
        *[services.payments.approve(admin if i % 2 else super_admin, payment.id) for i in range(5)],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)

    assert len(ok) == 1 and len(failed) == 4
    assert await services.wallet.balance_units(user.id) == 50_000
    deposits = [t for t in await repos.transactions.list_by_user(user.id, limit=20) if t.type == TransactionType.DEPOSIT]
    assert len(deposits) == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_approve_and_reject_race_has_single_winner(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, payment_method,
) -> None:
    """اعتماد ورفض في اللحظة نفسها ⇒ قرار واحد نهائي، ورصيد متسق مع القرار."""
    payment = await _pending_payment(services, user, payment_method.id, "TRX-RACE2")

    results = await asyncio.gather(
        services.payments.approve(admin, payment.id),
        services.payments.reject(super_admin, payment.id, "اختبار تزامن"),
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    assert len(ok) == 1
    final = await repos.payments.get(payment.id)
    assert final is not None
    balance = await services.wallet.balance_units(user.id)
    if final.status == PaymentStatus.APPROVED:
        assert balance == 50_000
    else:
        assert final.status == PaymentStatus.REJECTED and balance == 0
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_same_transaction_reference_cannot_be_used_twice_concurrently(
    services: ServiceContainer, repos: Repositories, user: User, payment_method,
) -> None:
    """نفس رقم الحوالة من تسجيلين متزامنين (R5: احتيال مرجع مكرر) ⇒ دفعة واحدة فقط."""
    results = await asyncio.gather(
        *[_pending_payment(services, user, payment_method.id, "TRX-DUP") for _ in range(4)],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)
    assert len(ok) == 1 and len(failed) == 3


async def test_concurrent_expiry_sweeps_expire_once(
    services: ServiceContainer, repos: Repositories, db: Database, user: User, payment_method,
) -> None:
    """3 مهام انتهاء صلاحية متزامنة ⇒ تنتهي الدفعة مرة واحدة ولا يتكرر الإشعار."""
    payment = await _pending_payment(services, user, payment_method.id, "TRX-EXP")
    async with db.transaction() as tx:
        await tx.execute("UPDATE payments SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (payment.id,))

    counts = await asyncio.gather(*[services.payments.expire_due() for _ in range(3)])

    assert sum(counts) == 1
    final = await repos.payments.get(payment.id)
    assert final is not None and final.status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0


# ======================================================================== #
#                              تسويات الأدمن اليدوية                         #
# ======================================================================== #


async def test_concurrent_manual_debits_cannot_overdraw(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
) -> None:
    """خصومات يدوية متزامنة تفوق الرصيد ⇒ لا رصيد سالب وكل خصم ناجح له حركة."""
    await _fund(services, user, super_admin, 100_000)

    results = await asyncio.gather(
        *[
            services.wallet.adjust_balance(
                target=user, amount_units=30_000, admin=admin, reason=f"تسوية {i}", credit=False
            )
            for i in range(10)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    balance = await services.wallet.balance_units(user.id)
    assert balance >= 0
    assert balance == 100_000 - 30_000 * len(ok)
    assert len(ok) <= 3
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


# ======================================================================== #
#                      حدود المستخدم تحت التزامن (Limits)                      #
# ======================================================================== #


async def test_pending_payments_limit_holds_under_concurrency(
    services: ServiceContainer, repos: Repositories, user: User, payment_method,
) -> None:
    """حد الطلبات المعلّقة (3) لا يُتجاوز بإرسال 8 طلبات شحن متزامنة بمراجع مختلفة."""
    results = await asyncio.gather(
        *[_pending_payment(services, user, payment_method.id, f"TRX-LIM-{i}") for i in range(8)],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)
    assert len(ok) == 3
    assert await repos.payments.count_pending_by_user(user.id) == 3


async def test_daily_order_limit_holds_under_concurrency(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """الحد اليومي للطلبات لا يُتجاوز بطلبات متزامنة."""
    await _fund(services, user, admin, 500_000)
    await services.settings.set("duplicate_order_window_minutes", 0)
    await services.settings.set("max_orders_per_day", 2)

    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link=f"https://instagram.com/day{i}", quantity=1000
            )
            for i in range(6)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)
    assert len(ok) == 2
    assert await repos.orders.count_by_user(user.id) == 2


async def test_same_client_request_id_returns_single_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """نفس مفتاح الطلب من 5 نداءات متزامنة ⇒ طلب واحد، والجميع يستلمون الطلب نفسه بلا أخطاء ولا خصم مكرر."""
    await _fund(services, user, admin, 100_000)
    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link="https://instagram.com/p/k", quantity=1000,
                client_request_id="req-fixed-1",
            )
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)
    assert not failed, failed
    assert {order.id for order in ok} == {ok[0].id}
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_concurrent_first_start_registers_user_once(
    services: ServiceContainer, repos: Repositories,
) -> None:
    """ثلاث /start متزامنة من مستخدم جديد ⇒ حساب واحد، ومرة واحدة فقط «أُنشئ الآن»."""
    results = await asyncio.gather(
        *[services.users.get_or_create(telegram_id=424242, username="racer", first_name="R") for _ in range(3)],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)
    assert not failed, failed
    assert sum(1 for _user, created in ok if created) == 1
    assert len({u.id for u, _c in ok}) == 1
    assert await repos.users.count_all() == 1


async def test_one_open_ticket_per_user_under_concurrency(
    services: ServiceContainer, repos: Repositories, user: User,
) -> None:
    """فتح 5 تذاكر متزامنة ⇒ تذكرة واحدة فقط (قاعدة «تذكرة مفتوحة واحدة لكل مستخدم»)."""
    results = await asyncio.gather(
        *[
            services.tickets.create_ticket(user, subject="مشكلة في الطلب", message="التفاصيل هنا كاملة", category="other")
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)
    assert len(ok) == 1


# ======================================================================== #
#                         الإشعارات والإذاعة تحت التزامن                      #
# ======================================================================== #


class _Sender:
    """مرسل بطيء يسجّل كل رسالة (يفرض تداخل عاملي الإرسال)."""

    def __init__(self) -> None:
        """قائمة الرسائل المرسلة."""
        self.sent: list[tuple[int, str]] = []

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """تسجيل رسالة بعد تأخير قصير."""
        await asyncio.sleep(0.005)
        self.sent.append((telegram_id, title))
        return len(self.sent)


async def test_two_notification_dispatchers_never_double_send(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """عاملا إرسال إشعارات متزامنان ⇒ كل إشعار يصل مرة واحدة فقط (لا رسائل مكررة للعميل)."""
    await _fund(services, user, admin, 500_000)
    await services.settings.set("duplicate_order_window_minutes", 0)
    for i in range(5):
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/n{i}", quantity=1000
        )
    queued = await services.notifications.queued_count()
    assert queued >= 5
    sender = _Sender()

    await asyncio.gather(
        services.notifications.dispatch_pending(sender, limit=50),
        services.notifications.dispatch_pending(sender, limit=50),
        services.notifications.dispatch_pending(sender, limit=50),
    )
    await services.notifications.dispatch_pending(sender, limit=50)

    assert len(sender.sent) == queued, f"أُرسل {len(sender.sent)} من {queued} (تكرار أو فقد)"
    assert await services.notifications.queued_count() == 0


async def test_two_broadcast_workers_never_double_send(
    services: ServiceContainer, repos: Repositories, super_admin: User,
) -> None:
    """عاملا إذاعة متزامنان على 12 مستلماً ⇒ كل مستلم يصله النص مرة واحدة والعدّادات تطابق الواقع."""
    for index in range(12):
        await services.users.get_or_create(telegram_id=700_000 + index, username=f"b{index}", first_name="B")
    broadcast = await services.broadcasts.create(super_admin, text="رسالة جماعية", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    delivered: list[int] = []

    async def sender(telegram_id: int, text: str, media_file_id, media_type) -> int:
        """إرسال بطيء مسجَّل."""
        await asyncio.sleep(0.005)
        delivered.append(telegram_id)
        return len(delivered)

    for _ in range(4):
        await asyncio.gather(
            services.broadcasts.send_batch(sender, limit=4),
            services.broadcasts.send_batch(sender, limit=4),
        )
    final = await services.broadcasts.get(super_admin, broadcast.id)

    assert len(delivered) == len(set(delivered)), "مستلم وصلته الرسالة مرتين"
    assert final.status == "completed"
    assert final.sent_count == len(delivered)


async def test_concurrent_ticket_close_notifies_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
) -> None:
    """5 إغلاقات متزامنة لنفس التذكرة ⇒ إغلاق واحد وإشعار واحد للمستخدم."""
    ticket = await services.tickets.create_ticket(user, subject="موضوع", message="نص التذكرة", category="other")
    results = await asyncio.gather(*[services.tickets.close(admin, ticket.id, "تم") for _ in range(5)], return_exceptions=True)
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert results.count(True) == 1
    inbox = await repos.notifications.list_for_user(user.id, limit=50)
    assert len([n for n in inbox if n.type == "ticket_closed"]) == 1, "إشعار الإغلاق تكرر أو فُقد"


async def test_concurrent_provider_creation_with_same_name_fails_cleanly(
    services: ServiceContainer, super_admin: User, repos: Repositories,
) -> None:
    """4 محاولات متزامنة لإنشاء مزود بنفس الاسم ⇒ واحد ينجح والبقية خطأ عربي مفهوم (لا IntegrityError خام)."""
    from core.exceptions import SMMBotError

    async def attempt():
        """محاولة إنشاء مزود."""
        return await services.providers.create_provider(
            super_admin, name="مزود متزامن", api_url="https://provider.example.com/api/v2", api_key="key-1234567890",
        )

    results = await asyncio.gather(*[attempt() for _ in range(4)], return_exceptions=True)
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(successes) == 1, results
    assert all(isinstance(f, SMMBotError) for f in failures), [type(f).__name__ for f in failures]


async def test_concurrent_payment_method_same_code_fails_cleanly(
    services: ServiceContainer, super_admin: User,
) -> None:
    """إنشاء طريقة شحن بنفس الكود 4 مرات متزامنة ⇒ واحدة تنجح والبقية خطأ تحقق عربي (لا IntegrityError)."""
    from core.exceptions import SMMBotError

    async def attempt():
        """محاولة إنشاء طريقة شحن."""
        return await services.payments.create_method(super_admin, name_ar="طريقة", code="dup_code")

    results = await asyncio.gather(*[attempt() for _ in range(4)], return_exceptions=True)
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(results) - len(failures) == 1, results
    assert all(isinstance(f, SMMBotError) for f in failures), [type(f).__name__ for f in failures]
```

## `tests/e2e/test_ledger_fuzz_phase11.py` (جديد)

```python
"""
المرحلة 11 — اختبار عشوائي موجَّه (Randomized Stateful Fuzz) للثوابت المحاسبية.

الفكرة: بدل توقّع السيناريوهات يدوياً، نُشغّل مئات العمليات العشوائية (بذور ثابتة قابلة للإعادة)
من كل نوع — شحن/اعتماد/رفض/إلغاء/طلبات/فشل مزود/استرجاع جزئي/تسويات الأدمن/انتهاء صلاحية —
ثم نتحقق من ثوابت **لا يجوز كسرها مهما كان الترتيب**:

    I1  الرصيد المخزَّن = مجموع الحركات (لكل مستخدم) ولا رصيد سالب.
    I2  لكل طلب خصم واحد بقيمته بالضبط، ومجموع استرجاعاته = `refund_amount_units` ≤ التكلفة.
    I3  اتساق الحالة النهائية مع المبلغ المسترجع (مكتمل=0 · ملغى/مسترجع=كامل · جزئي=أقل من الكامل).
    I4  سجل الحالات سلسلة متصلة وكل انتقال مسموح في آلة الحالة.
    I5  لا طلبان بنفس رقم المزود، ولا طلب أُنشئ عند المزود أكثر من مرة.
    I6  كل دفعة معتمدة لها حركة إيداع واحدة بالضبط، والمرفوضة/المنتهية بلا حركة.
    I7  بعد «تصريف» الطلبات لا طلب عالق في `submitting`.
"""

from __future__ import annotations

import os
import random

import pytest

from core.enums import FINAL_ORDER_STATUSES, OrderStatus, PaymentStatus, TransactionType
from core.exceptions import (
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    SMMBotError,
)
from core.order_state import can_transition
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

SEEDS = (1, 7, 42, 2026)
STEPS = 70


class World:
    """حالة عالم الاختبار: المستخدمون والعدّادات وكل ما يلزم لتنفيذ عملية عشوائية."""

    def __init__(self, services, repos, db, users, admin, super_admin, mock_service, mock_client, rng) -> None:
        """تخزين الاعتماديات."""
        self.services, self.repos, self.db = services, repos, db
        self.users, self.admin, self.super_admin = users, admin, super_admin
        self.service, self.client, self.rng = mock_service, mock_client, rng
        self.counter = 0
        self.method_id: int | None = None

    def next(self) -> int:
        """رقم تسلسلي فريد للروابط والمراجع."""
        self.counter += 1
        return self.counter

    async def order_ids(self, *statuses: str) -> list[int]:
        """معرّفات الطلبات (كلها أو بحالات معينة)."""
        if statuses:
            marks = ",".join("?" for _ in statuses)
            rows = await self.db.fetchall(f"SELECT id FROM orders WHERE status IN ({marks})", statuses)
        else:
            rows = await self.db.fetchall("SELECT id FROM orders")
        return [int(r["id"]) for r in rows]

    async def pay_ids(self, status: str) -> list[int]:
        """معرّفات الدفعات بحالة معينة."""
        rows = await self.db.fetchall("SELECT id FROM payments WHERE status = ?", (status,))
        return [int(r["id"]) for r in rows]


# ------------------------------- العمليات العشوائية ------------------------------- #


async def act_deposit(w: World) -> None:
    """طلب شحن ثم (اعتماد | رفض | إلغاء المستخدم | تركه معلّقاً)."""
    user = w.rng.choice(w.users)
    payment = await w.services.payments.create_payment(
        user, method_id=w.method_id, raw_amount=str(w.rng.randint(1, 30)),
        transaction_reference=f"TRX-{w.next()}", proof_file_id="p", proof_file_type="photo",
    )
    choice = w.rng.random()
    if choice < 0.6:
        await w.services.payments.approve(w.admin, payment.id)
    elif choice < 0.8:
        await w.services.payments.reject(w.admin, payment.id, "مرفوض عشوائياً")
    elif choice < 0.9:
        await w.services.payments.cancel_by_user(user, payment.id)


async def act_order(w: World) -> None:
    """طلب جديد (قد يفشل لنقص الرصيد وهذا مقبول)."""
    user = w.rng.choice(w.users)
    await w.services.orders.create_order(
        user, service_id=w.service.id, link=f"https://instagram.com/fz{w.next()}",
        quantity=w.rng.choice([100, 500, 1000, 2500]),
    )


async def act_provider_hiccup(w: World) -> None:
    """برمجة فشل للإرسال القادم (مؤقت/نهائي/غير مؤكد)."""
    w.client.fail_next_add = w.rng.choice(
        [ProviderTemporaryError("انقطاع"), ProviderPermanentError("رفض"), ProviderUncertainError("مهلة")]
    )


async def act_submit(w: World) -> None:
    """مهمة الإرسال."""
    await w.services.orders.process_pending_orders(limit=w.rng.randint(1, 5))


async def act_provider_progress(w: World) -> None:
    """المزود يغيّر حالة طلب عنده (اكتمال/جزئي/إلغاء) ثم تعمل المتابعة الآلية."""
    live = [oid for oid in await w.order_ids(OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS)]
    if live:
        order = await w.repos.orders.get(w.rng.choice(live))
        if order and order.provider_order_id in w.client.orders:
            kind = w.rng.choice(["Completed", "Partial", "Canceled", "In progress"])
            delivered = w.rng.randint(0, order.quantity - 1) if kind == "Partial" else None
            w.client.advance(order.provider_order_id, to=kind, delivered=delivered)
    await _due_now(w)
    await w.services.orders.process_due_orders()


async def _due_now(w: World) -> None:
    """تقديم موعد الفحص لكل الطلبات النشطة."""
    async with w.db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-30),),
        )


async def act_user_cancel(w: World) -> None:
    """إلغاء المستخدم لطلب منتظر."""
    pending = await w.order_ids(OrderStatus.PENDING)
    if pending:
        order = await w.repos.orders.get(w.rng.choice(pending))
        owner = next(u for u in w.users if u.id == order.user_id)
        await w.services.orders.cancel_by_user(owner, order.id)


async def act_admin_resolve(w: World) -> None:
    """الأدمن يحسم طلباً غير مؤكد أو يلغي/يُفشل طلباً غير نهائي."""
    pool = await w.order_ids(OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.PENDING, OrderStatus.SUBMITTED)
    if not pool:
        return
    oid = w.rng.choice(pool)
    if w.rng.random() < 0.5:
        await w.services.orders.admin_cancel(w.admin, oid, "إلغاء إداري عشوائي")
    else:
        await w.services.orders.admin_mark_failed(w.admin, oid, "فشل مؤكد إدارياً")


async def act_adjust(w: World) -> None:
    """تسوية يدوية (إضافة/خصم) من الأدمن الأعلى."""
    user = w.rng.choice(w.users)
    await w.services.wallet.adjust_balance(
        target=user, amount_units=w.rng.randint(1, 50) * 1000, admin=w.super_admin,
        reason="تسوية عشوائية", credit=w.rng.random() < 0.6,
    )


async def act_expire(w: World) -> None:
    """انتهاء صلاحية دفعات معلّقة."""
    async with w.db.transaction() as tx:
        await tx.execute("UPDATE payments SET expires_at = ? WHERE status = 'pending'", (iso_plus_seconds(-10),))
    await w.services.payments.expire_due()


ACTIONS = [
    (act_deposit, 18), (act_order, 30), (act_provider_hiccup, 6), (act_submit, 14),
    (act_provider_progress, 14), (act_user_cancel, 4), (act_admin_resolve, 4), (act_adjust, 5), (act_expire, 2),
]


# ----------------------------------- الثوابت ----------------------------------- #


async def check_invariants(w: World) -> None:
    """فحص كل الثوابت المحاسبية والتشغيلية (I1…I6)."""
    services, repos, db = w.services, w.repos, w.db

    # I1 — الرصيد = الدفتر ولا سالب
    for user in w.users:
        check = await services.wallet.verify_ledger(user.id)
        assert check.is_balanced, f"اختلال محاسبي للمستخدم {user.id}: فرق {check.difference_units}"
        assert check.stored_units >= 0, f"رصيد سالب للمستخدم {user.id}: {check.stored_units}"

    provider_ids: dict[str, int] = {}
    for oid in await w.order_ids():
        order = await repos.orders.get(oid)
        assert order is not None
        txs = await services.wallet.order_transactions(oid)

        # I2 — خصم واحد بقيمة الطلب، ومجموع الاسترجاع = المسجَّل على الطلب
        charges = [t.amount_units for t in txs if t.type == TransactionType.ORDER]
        refunds = sum(t.amount_units for t in txs if t.type in (TransactionType.REFUND, TransactionType.PARTIAL_REFUND))
        assert charges == [order.cost_units], f"طلب {oid}: الخصومات {charges} والتكلفة {order.cost_units}"
        assert refunds == order.refund_amount_units, f"طلب {oid}: استرجاع الدفتر {refunds} ≠ {order.refund_amount_units}"
        assert 0 <= order.refund_amount_units <= order.cost_units

        # I3 — اتساق الحالة مع المبلغ المسترجع
        if order.status == OrderStatus.COMPLETED:
            assert order.refund_amount_units == 0, f"طلب {oid} مكتمل ومعه استرجاع"
        elif order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELED):
            assert order.refund_amount_units == order.cost_units, f"طلب {oid} {order.status} باسترجاع ناقص"
        elif order.status == OrderStatus.PARTIAL:
            assert order.refund_amount_units < order.cost_units, f"طلب {oid} جزئي باسترجاع كامل"
        elif order.status not in FINAL_ORDER_STATUSES and order.status != OrderStatus.FAILED:
            assert order.refund_amount_units == 0, f"طلب {oid} غير منتهٍ ({order.status}) ومعه استرجاع"

        # I4 — سجل الحالات متصل ومسموح
        history = await repos.orders.history(oid)
        previous: str | None = None
        for row in history:
            assert row.from_status == previous, f"طلب {oid}: انقطاع في السجل عند {row.to_status}"
            if previous is not None:
                assert can_transition(previous, row.to_status), f"طلب {oid}: انتقال محظور {previous}→{row.to_status}"
            previous = row.to_status
        assert previous == order.status, f"طلب {oid}: آخر سجل {previous} ≠ الحالة {order.status}"

        # I5 — رقم المزود فريد
        if order.provider_order_id:
            assert order.provider_order_id not in provider_ids, "طلبان بنفس رقم المزود"
            provider_ids[order.provider_order_id] = oid
    assert len(w.client.orders) == len(provider_ids), "طلبات عند المزود أكثر من المسجَّلة محلياً (إرسال مزدوج)"

    # I6 — الدفعات والإيداعات
    deposits = await db.fetchall("SELECT payment_id FROM transactions WHERE type = 'deposit'")
    deposited = [int(r["payment_id"]) for r in deposits]
    assert len(deposited) == len(set(deposited)), "دفعة أُضيفت مرتين"
    assert set(deposited) == set(await w.pay_ids(PaymentStatus.APPROVED)), "دفعات معتمدة بلا إيداع أو العكس"


async def drain(w: World) -> None:
    """تصريف الطلبات: مزود سليم، تكرار الإرسال والمتابعة حتى الاستقرار (I7)."""
    w.client.fail_next_add = None
    w.client.always_fail_add = None
    for _ in range(25):
        await w.services.orders.process_pending_orders(limit=20)
        await _due_now(w)
        await w.services.orders.process_due_orders(limit=50)
        async with w.db.transaction() as tx:                # تجاوز انتظار إعادة المحاولة (backoff)
            await tx.execute("UPDATE orders SET next_check_at = ? WHERE status = 'pending'", (iso_plus_seconds(-30),))
    stuck = await w.order_ids(OrderStatus.SUBMITTING)
    assert not stuck, f"طلبات عالقة في submitting: {stuck}"


# -------------------------------------- الاختبار -------------------------------------- #


@pytest.mark.parametrize("seed", SEEDS)
async def test_random_operations_never_break_money_invariants(
    seed: int, services: ServiceContainer, repos: Repositories, db: Database, admin: User, super_admin: User,
    mock_service: Service, mock_client, payment_method,
) -> None:
    """عمليات عشوائية بالبذرة المحددة ثم تصريف ⇒ كل الثوابت المحاسبية سليمة."""
    rng = random.Random(seed)
    await services.settings.set("duplicate_order_window_minutes", 0)
    await services.settings.set("max_pending_payments_per_user", 50)
    users = [
        (await services.users.get_or_create(telegram_id=910_000 + i, username=f"fz{i}", first_name=f"F{i}"))[0]
        for i in range(4)
    ]
    world = World(services, repos, db, users, admin, super_admin, mock_service, mock_client, rng)
    world.method_id = payment_method.id
    # رصيد افتتاحي لضمان طلبات ناجحة كثيرة
    for user in users:
        await services.wallet.adjust_balance(target=user, amount_units=80_000, admin=super_admin, reason="افتتاحي", credit=True)

    actions, weights = zip(*ACTIONS, strict=True)
    executed = 0
    for step in range(STEPS):
        action = rng.choices(actions, weights=weights)[0]
        try:
            await action(world)
            executed += 1
        except SMMBotError:
            pass   # رفض منطقي مشروع (رصيد/حالة/حد…) — المهم ألا يترك أثراً مالياً
        if step % 10 == 9:
            await check_invariants(world)

    await drain(world)
    await check_invariants(world)
    if os.environ.get("FUZZ_DEBUG"):
        rows = await db.fetchall("SELECT status, COUNT(*) c FROM orders GROUP BY status")
        pays = await db.fetchall("SELECT status, COUNT(*) c FROM payments GROUP BY status")
        print("SEED", seed, "executed", executed, {r["status"]: r["c"] for r in rows}, {r["status"]: r["c"] for r in pays})
    assert executed > STEPS // 3, "معظم العمليات فشلت — الاختبار لا يغطي شيئاً"
    assert len(await world.order_ids()) >= 5, "عدد الطلبات قليل جداً لإثبات شيء"


async def test_invariant_checker_detects_corruption(
    services: ServiceContainer, repos: Repositories, db: Database, admin: User, super_admin: User,
    mock_service: Service, mock_client, payment_method,
) -> None:
    """اختبار الاختبار: لو أفسدنا الدفتر أو الطلب عمداً يجب أن تفشل الثوابت (لا نجاح أعمى)."""
    user = (await services.users.get_or_create(telegram_id=920_001, username="c1", first_name="C"))[0]
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="x", credit=True)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/corrupt", quantity=1000
    )
    await services.orders.process_pending_orders(limit=5)
    world = World(services, repos, db, [user], admin, super_admin, mock_service, mock_client, random.Random(0))
    await check_invariants(world)                       # سليم قبل العبث

    async with db.transaction() as tx:                  # (أ) إفساد الرصيد المخزَّن فقط
        await tx.execute("UPDATE users SET balance_units = balance_units + 1 WHERE id = ?", (user.id,))
    with pytest.raises(AssertionError, match="اختلال محاسبي"):
        await check_invariants(world)
    async with db.transaction() as tx:
        await tx.execute("UPDATE users SET balance_units = balance_units - 1 WHERE id = ?", (user.id,))

    async with db.transaction() as tx:                  # (ب) تسجيل استرجاع على الطلب بلا حركة مالية
        await tx.execute("UPDATE orders SET refund_amount_units = 5 WHERE id = ?", (order.id,))
    with pytest.raises(AssertionError):
        await check_invariants(world)
```

## `tests/e2e/test_scenarios_phase11.py` (جديد)

```python
"""
المرحلة 11 — مصفوفة السيناريوهات الشاملة (رحلات متعددة الخطوات عبر الخدمات الحقيقية).

(قائمة «البند 39» الأصلية غير متاحة، فالسيناريوهات مشتقّة من DoD والمخاطر R والقرارات A/D.)

كل سيناريو يتحقق من الأثر الكامل: الحالة · المال (الدفتر) · الإشعارات · التدقيق · عدم تكرار الإرسال.

    S1  R1  نتيجة إرسال غير مؤكدة ⇒ لا إعادة إرسال ⇒ الأدمن يحسم ⇒ استرجاع كامل
    S2  D5  رصيد المزود غير كافٍ ⇒ انتظار ⇒ نجاح بعد الشحن
    S3  D5  رصيد المزود غير كافٍ ⇒ تجاوز المهلة ⇒ فشل + استرجاع تلقائي
    S4  A8  تنفيذ جزئي ⇒ استرجاع الباقي فقط
    S5  D11 إلغاء قبل الإرسال ينجح، وبعده يُرفض بلا استرجاع
    S6  A10 انتهاء دفعة ⇒ لا يمكن اعتمادها لاحقاً ولا إيداع
    S7      مستخدم محظور: لا طلبات جديدة، والطلب الجاري يكتمل
    S8      وضع الصيانة: يمنع المستخدم ويستثني الأدمن، والطلب الجاري يكتمل
    S9  A12 قاطع الدائرة: تعطيل المزود بعد فشل متتالٍ ثم استئناف بلا فقد للطلبات
    S10 R8  رفض الصلاحيات (RBAC): لا أثر مالي ويُسجَّل حدث أمني
    S11 R12 اعتماد/رفض مزدوج لنفس الدفعة ⇒ إيداع واحد
    S12 R9  استرجاع تلقائي بعد فشل نهائي ⇒ مالياً صفر صافٍ وإشعار للمستخدم والأدمن
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus, PaymentStatus, TransactionType
from core.exceptions import (
    InvalidStateTransitionError,
    MaintenanceModeError,
    PermissionDeniedError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    SMMBotError,
    UserBannedError,
)
from database.database import Database
from database.models import Service, User
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

LINK = "https://instagram.com/scenario"


class Inbox:
    """مرسل إشعارات يجمع ما يصل لكل محادثة."""

    def __init__(self) -> None:
        """قائمة الرسائل."""
        self.messages: list[tuple[int, str, str]] = []

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """تسجيل رسالة."""
        self.messages.append((telegram_id, title, message))
        return len(self.messages)

    def text_for(self, telegram_id: int) -> str:
        """كل ما وصل لمحادثة معيّنة نصاً واحداً."""
        return "\n".join(f"{t}\n{m}" for chat, t, m in self.messages if chat == telegram_id)


async def _fund(services: ServiceContainer, user: User, super_admin: User, units: int = 100_000) -> None:
    """شحن رصيد عبر المسار الرسمي."""
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=super_admin, reason="رصيد", credit=True)


async def _order(services: ServiceContainer, user: User, service: Service, *, link: str = LINK, quantity: int = 1000):
    """إنشاء طلب."""
    return await services.orders.create_order(user, service_id=service.id, link=link, quantity=quantity)


async def _due(db: Database, order_id: int) -> None:
    """تقديم موعد الفحص/المحاولة."""
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), order_id))


async def _ledger_ok(services: ServiceContainer, *users: User) -> None:
    """الدفتر متوازن والرصيد غير سالب."""
    for user in users:
        check = await services.wallet.verify_ledger(user.id)
        assert check.is_balanced and check.stored_units >= 0


# ----------------------------------- S1 ----------------------------------- #


async def test_s1_uncertain_submit_no_resend_then_admin_refunds(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S1: غموض الإرسال لا يُعاد إرساله أبداً، وحسم الأدمن يُرجع المال مرة واحدة."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("انتهت المهلة")
    await services.orders.process_pending_orders()
    mock_client.always_fail_add = None                      # حتى لو عاد المزود سليماً لا نعيد الإرسال

    for _ in range(3):
        await _due(db, order.id)
        await services.orders.process_pending_orders()
        await services.orders.process_due_orders()
    adds = [c for c in mock_client.calls if c[0] == "add"]
    assert len(adds) == 1, "أُعيد إرسال طلب غير مؤكد"
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert await services.wallet.balance_units(user.id) == 90_000

    refunded = await services.orders.admin_mark_failed(admin, order.id, "تأكدنا من لوحة المزود")
    assert refunded == 10_000 and await services.wallet.balance_units(user.id) == 100_000
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_mark_failed(admin, order.id, "مرة ثانية")
    assert await services.wallet.balance_units(user.id) == 100_000
    audit = await db.fetchall("SELECT 1 FROM audit_logs WHERE action = 'orders.refund' AND target_id = ?", (order.id,))
    assert len(audit) == 1
    inbox = Inbox()
    await services.notifications.dispatch_pending(inbox, limit=100)
    assert inbox.text_for(user.telegram_id), "لم يُبلَّغ المستخدم بنتيجة الحسم"
    await _ledger_ok(services, user)


# --------------------------------- S2 / S3 --------------------------------- #


async def test_s2_provider_out_of_funds_waits_then_succeeds_after_topup(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S2: رصيد المزود غير كافٍ ⇒ يبقى pending دون خصم مضاعف، وينفَّذ بعد شحن المزود."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.balance_units = 0
    report = await services.orders.process_pending_orders()
    assert report.succeeded == 0
    current = await repos.orders.get(order.id)
    assert current.status == OrderStatus.PENDING and current.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000
    assert await repos.notifications.count_queued() >= 1, "يجب تنبيه الأدمن برصيد المزود"

    mock_client.balance_units = 1_000_000                   # الأدمن شحن حساب المزود
    await _due(db, order.id)
    await services.orders.process_pending_orders()
    done = await repos.orders.get(order.id)
    assert done.status in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS) and done.provider_order_id
    assert len(await repos.transactions.list_by_order(order.id)) == 1      # خصم واحد فقط
    await _ledger_ok(services, user)


async def test_s3_provider_out_of_funds_past_deadline_fails_and_refunds(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S3: بعد المهلة القصوى يفشل الطلب ويُسترجع المبلغ كاملاً مرة واحدة."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.balance_units = 0
    async with db.transaction() as tx:                      # عمر الطلب 7 ساعات > مهلة 6 ساعات
        await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (iso_plus_seconds(-7 * 3600), order.id))
    await services.orders.process_pending_orders()
    current = await repos.orders.get(order.id)
    assert current.status in (OrderStatus.FAILED, OrderStatus.REFUNDED)
    assert current.refund_amount_units == 10_000
    assert await services.wallet.balance_units(user.id) == 100_000
    refunds = [t for t in await repos.transactions.list_by_order(order.id) if t.type == TransactionType.REFUND]
    assert len(refunds) == 1
    await _ledger_ok(services, user)


# ----------------------------------- S4 ----------------------------------- #


async def test_s4_partial_refunds_only_the_remaining_quantity(
    services, repos, db, user, super_admin, mock_service, mock_client
) -> None:
    """S4: تسليم 250 من 1000 ⇒ استرجاع 75% فقط، وإعادة الفحص لا تكرر الاسترجاع."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    await services.orders.process_pending_orders()
    pid = (await repos.orders.get(order.id)).provider_order_id
    mock_client.advance(pid, to="Partial", delivered=250)
    for _ in range(3):
        await _due(db, order.id)
        await services.orders.process_due_orders()
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.PARTIAL and final.delivered_quantity == 250
    assert final.refund_amount_units == 7_500
    assert await services.wallet.balance_units(user.id) == 97_500
    await _ledger_ok(services, user)


# ----------------------------------- S5 ----------------------------------- #


async def test_s5_cancel_allowed_only_before_submission(
    services, repos, db, user, super_admin, mock_service, mock_client
) -> None:
    """S5: الإلغاء قبل الإرسال ⇒ استرجاع كامل؛ بعد الإرسال ⇒ رفض وبلا أي أثر مالي."""
    await _fund(services, user, super_admin)
    early = await _order(services, user, mock_service, link=LINK + "/a")
    assert await services.orders.cancel_by_user(user, early.id) == 10_000
    assert (await repos.orders.get(early.id)).status in (OrderStatus.CANCELED, OrderStatus.REFUNDED)

    late = await _order(services, user, mock_service, link=LINK + "/b")
    await services.orders.process_pending_orders()
    balance = await services.wallet.balance_units(user.id)
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.cancel_by_user(user, late.id)
    assert await services.wallet.balance_units(user.id) == balance
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.cancel_by_user(user, early.id)           # لا استرجاع مزدوج
    await _ledger_ok(services, user)


# ----------------------------------- S6 ----------------------------------- #


async def test_s6_expired_payment_cannot_be_approved(
    services, repos, db, user, admin, payment_method
) -> None:
    """S6: دفعة انتهت مهلتها ⇒ حالتها منتهية ولا إيداع عند محاولة اعتمادها."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="EXP-1",
        proof_file_id="p", proof_file_type="photo",
    )
    async with db.transaction() as tx:
        await tx.execute("UPDATE payments SET expires_at = ? WHERE id = ?", (iso_plus_seconds(-5), payment.id))
    assert await services.payments.expire_due() >= 1
    with pytest.raises(SMMBotError):
        await services.payments.approve(admin, payment.id)
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0
    await _ledger_ok(services, user)


# --------------------------------- S7 / S8 --------------------------------- #


async def test_s7_banned_user_blocked_but_inflight_order_completes(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S7: الحظر يمنع الجديد، ولا يترك طلباً مدفوعاً معلّقاً بلا نهاية."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    await services.orders.process_pending_orders()
    await services.users.ban(admin, user.id, "مخالفة")
    banned = await repos.users.get_by_id(user.id)
    with pytest.raises(UserBannedError):
        await _order(services, banned, mock_service, link=LINK + "/new")
    for _ in range(4):
        await _due(db, order.id)
        await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    await _ledger_ok(services, user)


async def test_s8_maintenance_blocks_users_not_admins_and_inflight_continues(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S8: وضع الصيانة يوقف طلبات المستخدمين الجديدة فقط."""
    await _fund(services, user, super_admin)
    await _fund(services, admin, super_admin)
    order = await _order(services, user, mock_service)
    await services.orders.process_pending_orders()
    await services.settings.set("maintenance_mode", True, admin_id=super_admin.id)
    with pytest.raises(MaintenanceModeError):
        await _order(services, user, mock_service, link=LINK + "/m")
    assert (await _order(services, admin, mock_service, link=LINK + "/adm")).status == OrderStatus.PENDING
    for _ in range(4):
        await _due(db, order.id)
        await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    await _ledger_ok(services, user, admin)


# ----------------------------------- S9 ----------------------------------- #


async def test_s9_circuit_breaker_pauses_provider_then_resumes_without_loss(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S9: بعد فشل متتالٍ يُعطَّل المزود مؤقتاً (لا مزيد من المحاولات) ثم يُستأنف بلا فقد."""
    await _fund(services, user, super_admin)
    threshold = await services.settings.get_int("provider_failure_threshold", 5)
    orders = [await _order(services, user, mock_service, link=f"{LINK}/cb{i}") for i in range(threshold + 2)]
    mock_client.always_fail_add = ProviderTemporaryError("انقطاع")
    for _ in range(threshold + 3):
        for o in orders:
            await _due(db, o.id)
        await services.orders.process_pending_orders(limit=50)
    provider_id = (await repos.orders.get(orders[0].id)).provider_id
    disabled = await repos.providers.get(provider_id)
    assert disabled.disabled_until, "لم يُعطَّل المزود بعد الفشل المتتالي"

    attempts = len([c for c in mock_client.calls if c[0] == "add"])
    for o in orders:
        await _due(db, o.id)
    await services.orders.process_pending_orders(limit=50)
    assert len([c for c in mock_client.calls if c[0] == "add"]) == attempts, "محاولات إرسال أثناء التعطيل"
    for o in orders:
        assert (await repos.orders.get(o.id)).refund_amount_units == 0, "استرجاع خاطئ بسبب فشل مؤقت"

    mock_client.always_fail_add = None                      # المزود عاد + انتهى التعطيل
    async with db.transaction() as tx:
        await tx.execute("UPDATE providers SET disabled_until = NULL, consecutive_failures = 0 WHERE id = ?", (provider_id,))
    for o in orders:
        await _due(db, o.id)
    await services.orders.process_pending_orders(limit=50)
    states = [(await repos.orders.get(o.id)).status for o in orders]
    assert all(s in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS) for s in states), states
    assert len({(await repos.orders.get(o.id)).provider_order_id for o in orders}) == len(orders)
    await _ledger_ok(services, user)


# ---------------------------------- S10 ---------------------------------- #


async def test_s10_rbac_denials_have_no_financial_effect(
    services, repos, db, user, admin, super_admin, mock_service, payment_method
) -> None:
    """S10: مستخدم عادي ودور دعم يحاولان عمليات إدارية ⇒ رفض + لا تغيير رصيد + حدث أمني."""
    support = (await services.users.get_or_create(telegram_id=930_001, username="sup", first_name="S"))[0]
    async with db.transaction() as tx:
        await tx.execute("UPDATE users SET role = 'support' WHERE id = ?", (support.id,))
    support = await repos.users.get_by_id(support.id)
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="RB-1",
        proof_file_id="p", proof_file_type="photo",
    )
    for actor in (user, support):
        with pytest.raises(PermissionDeniedError):
            await services.payments.approve(actor, payment.id)
        with pytest.raises(PermissionDeniedError):
            await services.wallet.adjust_balance(target=user, amount_units=1_000_000, admin=actor, reason="x", credit=True)
        with pytest.raises(PermissionDeniedError):
            await services.backups.create(actor)
    assert await services.wallet.balance_units(user.id) == 0
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.PENDING
    events = await db.fetchall("SELECT 1 FROM audit_logs WHERE action LIKE 'security.%'")
    assert len(events) >= 3, "الرفض لم يُسجَّل كحدث أمني"
    await _ledger_ok(services, user)


# ---------------------------------- S11 ---------------------------------- #


async def test_s11_double_approve_and_approve_then_reject_credit_once(
    services, repos, db, user, admin, super_admin, payment_method
) -> None:
    """S11: اعتماد مكرر أو رفض بعد الاعتماد لا يغيّر الرصيد."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="DA-1",
        proof_file_id="p", proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id)
    with pytest.raises(SMMBotError):
        await services.payments.approve(super_admin, payment.id)
    with pytest.raises(SMMBotError):
        await services.payments.reject(admin, payment.id, "متأخر")
    assert await services.wallet.balance_units(user.id) == 50_000
    deposits = [t for t in await repos.transactions.list_by_user(user.id) if t.type == TransactionType.DEPOSIT]
    assert len(deposits) == 1
    await _ledger_ok(services, user)


# ---------------------------------- S12 ---------------------------------- #


async def test_s12_permanent_failure_refunds_and_notifies_user_and_admin(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S12: المسار البديل الكامل: رفض نهائي ⇒ استرجاع ⇒ حركة مالية ⇒ إشعار للمستخدم والأدمن."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = ProviderPermanentError("رابط غير صالح")
    await services.orders.process_pending_orders()
    final = await repos.orders.get(order.id)
    assert final.status in (OrderStatus.FAILED, OrderStatus.REFUNDED)
    assert await services.wallet.balance_units(user.id) == 100_000
    kinds = sorted(t.type for t in await repos.transactions.list_by_order(order.id))
    assert kinds == [TransactionType.ORDER, TransactionType.REFUND]
    inbox = Inbox()
    await services.notifications.dispatch_pending(inbox, limit=100)
    assert inbox.text_for(user.telegram_id), "لم يصل المستخدم إشعار"
    assert inbox.text_for(admin.telegram_id) or inbox.text_for(super_admin.telegram_id), "لم يصل الأدمن إشعار"
    await _ledger_ok(services, user)
```

## `tests/e2e/test_dispatcher_phase11.py` (جديد)

```python
"""
المرحلة 11 — اختبار الموزّع الحقيقي (`telegram.ext.Application`) بلا شبكة.

الفرق عن بقية الاختبارات: هنا لا نستدعي المعالجات مباشرة ولا نستعمل بوتاً مزيّفاً، بل:

    تحديث JSON ⇒ `Update.de_json` ⇒ `Application.process_update` ⇒ المعالجات المسجَّلة فعلياً
    عبر `register_handlers` (المجموعات والـConversationHandler والطبقة الوسيطة ومعالج الأخطاء)
    ⇒ `Bot` حقيقي (Defaults + تسلسل JSON) ⇒ طلب HTTP يعترضه `RecordingRequest` بدل الشبكة.

وبذلك تُختبر هندسة التوجيه نفسها: أولوية المجموعات، التقاط الأزرار، الحظر، الصيانة، حد المعدل،
وأن ضغط **كل** زر يصل لمعالج حقيقي دون استثناء غير معالَج.
"""

from __future__ import annotations

import itertools
import json
import time
from collections import deque
from typing import Any

import pytest
import pytest_asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, Defaults, ExtBot
from telegram.request import BaseRequest, RequestData

from handlers.registry import build_handlers, register_handlers
from services import ServiceContainer

pytestmark = pytest.mark.asyncio

BOT_ID = 123456789
TOKEN = f"{BOT_ID}:AADispatcherTestDummyTokenNeverUsedOnline"
_ids = itertools.count(1)


class RecordingRequest(BaseRequest):
    """بديل طبقة HTTP: يسجّل كل استدعاء لـBot API ويردّ بما يردّ به تيليجرام عادةً."""

    def __init__(self) -> None:
        """قائمة الاستدعاءات (الطريقة، المعاملات)."""
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def initialize(self) -> None:
        """لا موارد للتهيئة."""

    async def shutdown(self) -> None:
        """لا موارد للإغلاق."""

    @property
    def read_timeout(self) -> float | None:
        """مهلة القراءة (غير مستعملة)."""
        return 1.0

    async def do_request(self, url: str, method: str, request_data: RequestData | None = None, **_: Any) -> tuple[int, bytes]:
        """تسجيل الاستدعاء وتركيب ردّ شبيه بردّ تيليجرام."""
        endpoint = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((endpoint, params))
        if endpoint == "getMe":
            result: Any = {"id": BOT_ID, "is_bot": True, "first_name": "Bot", "username": "dispatcher_bot"}
        elif endpoint in {"sendMessage", "editMessageText", "sendPhoto", "sendDocument", "editMessageReplyMarkup"}:
            result = {
                "message_id": next(_ids), "date": int(time.time()),
                "chat": {"id": int(params.get("chat_id", 0) or 0), "type": "private"},
                "text": str(params.get("text", "")),
            }
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


class Harness:
    """غلاف يبسّط إرسال التحديثات واستخراج آخر ردّ وأزراره."""

    def __init__(self, app: Application, request: RecordingRequest, services: ServiceContainer) -> None:
        """تخزين التطبيق وسجل الطلبات."""
        self.app, self.request, self.services = app, request, services

    @property
    def calls(self) -> list[tuple[str, dict[str, Any]]]:
        """كل الاستدعاءات المسجَّلة بعد التهيئة."""
        return self.request.calls

    def mark(self) -> int:
        """علامة موضع في السجل لقياس ما بعدها."""
        return len(self.request.calls)

    def since(self, mark: int, *endpoints: str) -> list[dict[str, Any]]:
        """معاملات الاستدعاءات (من نوع معيّن) بعد علامة."""
        return [p for e, p in self.request.calls[mark:] if not endpoints or e in endpoints]

    async def say(self, user_id: int, text: str, *, first_name: str = "Tester") -> None:
        """إرسال رسالة نصية (تُفسَّر كأمر إن بدأت بـ/)."""
        message: dict[str, Any] = {
            "message_id": next(_ids), "date": int(time.time()),
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": first_name},
            "text": text,
        }
        if text.startswith("/"):
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        await self.app.process_update(Update.de_json({"update_id": next(_ids), "message": message}, self.app.bot))

    def unthrottle(self, user_id: int) -> None:
        """تصفير حد المعدل وحارس الإساءة (لاختبارات التصفح الطويلة التي ليست عن الحد نفسه)."""
        self.app.bot_data["rate_limiter"].reset(user_id)
        self.app.bot_data["abuse_guard"].clear(user_id)

    async def press(self, user_id: int, data: str) -> None:
        """ضغط زر inline يحمل `callback_data`."""
        payload = {
            "update_id": next(_ids),
            "callback_query": {
                "id": f"cb{next(_ids)}", "chat_instance": "ci", "data": data,
                "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
                "message": {
                    "message_id": next(_ids), "date": int(time.time()),
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": BOT_ID, "is_bot": True, "first_name": "Bot"}, "text": "شاشة",
                },
            },
        }
        await self.app.process_update(Update.de_json(payload, self.app.bot))

    def last_buttons(self, mark: int) -> list[str]:
        """أزرار callback في آخر رسالة/تعديل بعد العلامة."""
        for endpoint, params in reversed(self.request.calls[mark:]):
            if endpoint in {"sendMessage", "editMessageText", "editMessageReplyMarkup"} and "reply_markup" in params:
                raw = params["reply_markup"]
                markup = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                return [b["callback_data"] for row in markup.get("inline_keyboard", []) for b in row if "callback_data" in b]
        return []

    def texts(self, mark: int) -> str:
        """نص كل ما أُرسل/عُدِّل بعد العلامة."""
        return "\n".join(str(p.get("text", "")) for p in self.since(mark, "sendMessage", "editMessageText"))

    async def error_count(self) -> int:
        """عدد سجلات الأخطاء المخزَّنة (يجب أن يبقى صفراً)."""
        row = await self.services.db.fetchone("SELECT COUNT(*) AS c FROM error_logs")
        return int(row["c"])


@pytest_asyncio.fixture
async def harness(services: ServiceContainer):
    """تطبيق حقيقي بكل المعالجات المسجَّلة وخدمات حقيقية، وشبكة مُعترَضة."""
    request = RecordingRequest()
    bot = ExtBot(TOKEN, request=request, defaults=Defaults(parse_mode=ParseMode.HTML, disable_web_page_preview=True))
    app = ApplicationBuilder().bot(bot).concurrent_updates(False).build()
    app.bot_data["services"] = services
    register_handlers(app)
    await app.initialize()
    yield Harness(app, request, services)
    await app.shutdown()


async def _promote(services: ServiceContainer, telegram_id: int, role: str) -> None:
    """رفع دور مستخدم مباشرة في القاعدة (إعداد الاختبار فقط)."""
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))


# ----------------------------------- الاختبارات ----------------------------------- #


async def test_registered_handler_count_matches_registry(harness: Harness) -> None:
    """عدد المعالجات الفعلي على التطبيق = ما يبنيه السجل + الطبقة الوسيطة تعمل في المجموعة الأولى."""
    total = sum(len(handlers) for handlers in harness.app.handlers.values())
    assert total == len(build_handlers()) == 146
    assert min(harness.app.handlers) < 0 or 0 in harness.app.handlers


async def test_start_registers_user_and_shows_main_menu_with_html_defaults(harness: Harness) -> None:
    """/start لمستخدم جديد ⇒ صف في القاعدة + قائمة رئيسية بأزرار + parse_mode=HTML من Defaults."""
    mark = harness.mark()
    await harness.say(501_001, "/start")
    user = await harness.services.users.get_by_telegram(501_001)
    assert user is not None and not user.is_banned
    sent = harness.since(mark, "sendMessage")
    assert sent, "لم تُرسل أي رسالة ردّاً على /start"
    assert sent[-1]["parse_mode"] == "HTML"
    assert len(harness.last_buttons(mark)) >= 4, "القائمة الرئيسية بلا أزرار كافية"
    assert await harness.error_count() == 0


async def test_every_main_menu_button_reaches_a_real_handler(harness: Harness) -> None:
    """ضغط كل زر في القائمة الرئيسية ثم أزرار الشاشات الناتجة (BFS) ⇒ كل ضغطة تُجاب بلا خطأ."""
    uid = 501_002
    mark = harness.mark()
    await harness.say(uid, "/start")
    queue = deque(harness.last_buttons(mark))
    seen: set[str] = set()
    pressed = 0
    while queue and pressed < 150:
        data = queue.popleft()
        if data in seen:
            continue
        seen.add(data)
        before = harness.mark()
        harness.unthrottle(uid)
        await harness.press(uid, data)
        pressed += 1
        answered = harness.since(before, "answerCallbackQuery")
        replied = harness.since(before, "sendMessage", "editMessageText", "editMessageReplyMarkup")
        assert answered or replied, f"زر ميّت: {data}"
        queue.extend(b for b in harness.last_buttons(before) if b not in seen)
    assert pressed >= 10, "عدد الأزرار المفحوصة قليل جداً"
    assert await harness.error_count() == 0, "استثناء غير معالَج أثناء الضغط على الأزرار"


async def test_every_admin_panel_button_reaches_a_real_handler(harness: Harness, services: ServiceContainer) -> None:
    """نفس الفحص للوحة الأدمن الأعلى: لا زر ميّت ولا استثناء غير معالَج."""
    uid = 501_003
    await harness.say(uid, "/start")
    await _promote(services, uid, "super_admin")
    mark = harness.mark()
    await harness.say(uid, "/admin")
    start = harness.last_buttons(mark)
    assert len(start) >= 8, "لوحة الأدمن بلا أقسام كافية"
    queue = deque(start)
    seen: set[str] = set()
    history: list[str] = []
    pressed = 0
    while queue and pressed < 400:
        data = queue.popleft()
        if data in seen:
            continue
        seen.add(data)
        before = harness.mark()
        harness.unthrottle(uid)
        await harness.press(uid, data)
        pressed += 1
        history.append(data)
        assert harness.since(before), f"زر ميّت في لوحة الأدمن: {data} (سبقه: {history[-5:-1]})"
        queue.extend(b for b in harness.last_buttons(before) if b not in seen)
    assert pressed >= 30
    assert await harness.error_count() == 0, "استثناء غير معالَج في لوحة الأدمن"


async def test_regular_user_cannot_open_admin_panel(harness: Harness) -> None:
    """/admin من مستخدم عادي ⇒ لا لوحة ولا أزرار إدارية."""
    await harness.say(501_004, "/start")
    mark = harness.mark()
    await harness.say(501_004, "/admin")
    assert not harness.last_buttons(mark) or "admin" not in " ".join(harness.last_buttons(mark)).lower()
    events = await harness.services.db.fetchall("SELECT 1 FROM audit_logs WHERE action LIKE 'security.%'")
    assert events, "محاولة الدخول غير المصرّح بها لم تُسجَّل"


async def test_banned_user_gets_no_menu_and_no_state_change(harness: Harness, services: ServiceContainer) -> None:
    """مستخدم محظور: /start وضغط الأزرار لا يفتحان أي قائمة."""
    uid = 501_005
    await harness.say(uid, "/start")
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE users SET is_banned = 1 WHERE telegram_id = ?", (uid,))
    mark = harness.mark()
    await harness.say(uid, "/start")
    assert not harness.last_buttons(mark), "المحظور رأى قائمة"
    mark = harness.mark()
    await harness.press(uid, "menu:main")
    assert not harness.last_buttons(mark)
    assert await harness.error_count() == 0


async def test_maintenance_blocks_user_but_not_super_admin(harness: Harness, services: ServiceContainer) -> None:
    """وضع الصيانة: المستخدم يرى رسالة الصيانة، والأدمن الأعلى يدخل لوحته."""
    admin_id, user_id = 501_006, 501_007
    await harness.say(admin_id, "/start")
    await _promote(services, admin_id, "super_admin")
    await services.settings.set("maintenance_mode", True, admin_id=None)
    await services.settings.set("maintenance_message", "صيانة تجريبية", admin_id=None)
    mark = harness.mark()
    await harness.say(user_id, "/start")
    assert "صيانة تجريبية" in harness.texts(mark)
    mark = harness.mark()
    await harness.say(admin_id, "/admin")
    assert len(harness.last_buttons(mark)) >= 8
    assert await harness.error_count() == 0


async def test_flood_is_throttled_without_crash(harness: Harness) -> None:
    """إغراق بـ60 ضغطة سريعة ⇒ يُقيَّد المستخدم ويبقى النظام سليماً (لا استثناء)."""
    uid = 501_008
    await harness.say(uid, "/start")
    mark = harness.mark()
    for _ in range(60):
        await harness.press(uid, "menu:main")
    replies = harness.since(mark, "editMessageText", "sendMessage")
    assert len(replies) < 60, "لم يُطبَّق حد المعدل"
    assert await harness.error_count() == 0


async def test_unknown_text_and_unknown_callback_are_handled_gracefully(harness: Harness) -> None:
    """نص عشوائي وcallback مجهول/تالف ⇒ ردّ لطيف أو تجاهل، دون استثناء غير معالَج."""
    uid = 501_009
    await harness.say(uid, "/start")
    for text in ("مرحبا", "/nonexistent", "a" * 3000, "<b>x</b>", "'; DROP TABLE users;--"):
        await harness.say(uid, text)
    for data in ("zzz", "x:y:z:1", "", "o:" + "9" * 40, "menu:main:v999"):
        await harness.press(uid, data or "-")
    assert await harness.error_count() == 0
    count = await harness.services.db.fetchone("SELECT COUNT(*) AS c FROM users")
    assert int(count["c"]) == 1


async def test_error_handler_reports_and_user_sees_friendly_message(harness: Harness, services: ServiceContainer, monkeypatch) -> None:
    """خلل داخلي حقيقي داخل معالج ⇒ معالج الأخطاء يسجّل ويعتذر للمستخدم بلا تسريب تفاصيل."""
    uid = 501_010
    await harness.say(uid, "/start")

    boom_calls: list[int] = []

    async def boom(*_a: Any, **_k: Any) -> Any:
        """خلل مفتعل."""
        boom_calls.append(1)
        raise RuntimeError("SECRET-INTERNAL-DETAIL")

    monkeypatch.setattr(services.wallet, "history", boom)
    monkeypatch.setattr(services.catalog, "categories", boom)
    mark = harness.mark()
    for data in harness.last_buttons(0)[:8]:
        harness.unthrottle(uid)
        await harness.press(uid, data)
    visible = harness.texts(mark)
    assert "SECRET-INTERNAL-DETAIL" not in visible, "تسريب تفاصيل داخلية للمستخدم"
    assert boom_calls, "الخلل المفتعل لم يُستدعَ أصلاً — الاختبار فارغ"
    assert visible.strip(), "المستخدم لم يتلقَّ أي اعتذار"
    assert await harness.error_count() >= 1, "الخطأ لم يُسجَّل في error_logs"
```

## `tests/unit/test_code_quality_phase11.py` (جديد)

```python
"""
المرحلة 11 — بوابة جودة الكود (تحليل ساكن بـ`ast`) على كل شيفرة الإنتاج.

تُنفِّذ آلياً بنود «الممنوعات» و«تعريف الإنجاز» التي كانت تُراجَع يدوياً:

    • لا `except:` عارٍ ولا معالج استثناء صامت (`pass`/`continue`/نص فقط).
    • لا `except Exception/BaseException` بلا تسجيل أو إعادة رفع.
    • كل دالة لها docstring **عربي** (شرط التعليقات العربية بجانب كل دالة).
    • لا TODO/FIXME/XXX/HACK، ولا `eval/exec`، ولا `shell=True`.
    • لا أسرار مضمَّنة (توكن بوت، مفتاح Fernet، كلمة مرور/مفتاح API نصي).
    • لا `print` خارج نقاط الدخول وسكربتات CLI.
    • كل SQL يحتوي قيماً متغيرة يستعمل معاملات `?` (لا f-string فيها قيم مستخدم): نفحص أن f-strings
      في `execute/fetch*` لا تُدخل إلا أسماء مُعرَّفة من الكود (قائمة مسموح بها).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"tests", ".venv", "venv", "__pycache__", "logs", "data", "backups", ".git", "node_modules"}
ARABIC = re.compile(r"[\u0600-\u06FF]")
#: نقاط الدخول/أدوات التطوير المسموح لها بـprint (إخراج للمشغّل)
PRINT_ALLOWED = ("scripts/", "main.py", "docs/")
#: أسرار مُعلنة كقيم وهمية صريحة (تحوي كلمة Dummy) مسموحة
DUMMY_MARK = "dummy"


def _files() -> list[Path]:
    """كل ملفات بايثون الإنتاجية في المشروع."""
    result = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        result.append(path)
    return result


def _parse(path: Path) -> tuple[ast.AST, str]:
    """قراءة الملف وتحليله."""
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path)), source


def _rel(path: Path) -> str:
    """مسار نسبي للعرض."""
    return path.relative_to(ROOT).as_posix()


def _handlers(tree: ast.AST):
    """كل معالجات except في شجرة."""
    return [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]


def test_there_is_production_code_to_scan() -> None:
    """حارس: ألا يصير الاختبار فارغاً لو تغيّر موضع الملفات."""
    assert len(_files()) > 100


def test_no_bare_except_and_no_silent_handlers() -> None:
    """لا `except:` عارٍ، ولا معالج جسمه pass/continue/تعبير ثابت فقط."""
    offenders = []
    for path in _files():
        tree, _ = _parse(path)
        for handler in _handlers(tree):
            if handler.type is None:
                offenders.append(f"{_rel(path)}:{handler.lineno} except عارٍ")
            silent = all(
                isinstance(stmt, (ast.Pass, ast.Continue))
                or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
                for stmt in handler.body
            )
            if silent:
                offenders.append(f"{_rel(path)}:{handler.lineno} معالج صامت")
    assert not offenders, "\n".join(offenders)


def test_broad_exception_handlers_always_log_or_reraise() -> None:
    """`except Exception` مسموح فقط إن سُجّل الخطأ أو أُعيد رفعه (لا إخفاء أخطاء)."""
    offenders = []
    for path in _files():
        tree, _ = _parse(path)
        for handler in _handlers(tree):
            if handler.type is None:
                continue
            names = {ast.unparse(handler.type)} if not isinstance(handler.type, ast.Tuple) else {ast.unparse(e) for e in handler.type.elts}
            if not names & {"Exception", "BaseException"}:
                continue
            body = ast.unparse(ast.Module(body=handler.body, type_ignores=[]))
            handled = "raise" in body or "logger." in body or "log" in body.lower() or "report" in body.lower()
            if not handled:
                offenders.append(f"{_rel(path)}:{handler.lineno}")
    assert not offenders, "except واسع بلا تسجيل/رفع:\n" + "\n".join(offenders)


def test_every_function_has_arabic_docstring() -> None:
    """كل دالة (حتى الداخلية) لها docstring يحوي عربية — شرط المالك الأهم."""
    missing, not_arabic = [], []
    for path in _files():
        tree, _ = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if not doc:
                    missing.append(f"{_rel(path)}:{node.lineno} {node.name}")
                elif not ARABIC.search(doc):
                    not_arabic.append(f"{_rel(path)}:{node.lineno} {node.name}")
    assert not missing, "دوال بلا docstring:\n" + "\n".join(missing)
    assert not not_arabic, "docstring بلا عربية:\n" + "\n".join(not_arabic)


def test_no_todo_markers_eval_exec_or_shell() -> None:
    """لا علامات إنجاز ناقص ولا تنفيذ ديناميكي خطِر."""
    offenders = []
    marker = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
    for path in _files():
        tree, source = _parse(path)
        if _rel(path) != "tests/unit/test_code_quality_phase11.py":
            for number, line in enumerate(source.splitlines(), 1):
                if marker.search(line):
                    offenders.append(f"{_rel(path)}:{number} علامة ناقصة")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                offenders.append(f"{_rel(path)}:{node.lineno} {node.func.id}")
            if isinstance(node, ast.keyword) and node.arg == "shell":
                offenders.append(f"{_rel(path)}:{node.value.lineno} shell=")
    assert not offenders, "\n".join(offenders)


def test_no_hardcoded_secrets() -> None:
    """لا توكن بوت ولا مفتاح Fernet ولا قيمة سرية نصية مضمَّنة (إلا قيماً وهمية معلنة)."""
    token = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
    fernet = re.compile(r"\b[A-Za-z0-9_-]{43}=(?![A-Za-z0-9])")
    assign = re.compile(r"""(?i)\b(api_?key|password|passwd|secret|token)\s*=\s*["'][^"'\s]{8,}["']""")
    offenders = []
    for path in _files():
        _, source = _parse(path)
        for number, line in enumerate(source.splitlines(), 1):
            if DUMMY_MARK in line.lower():
                continue
            if token.search(line) or fernet.search(line) or assign.search(line):
                offenders.append(f"{_rel(path)}:{number}: {line.strip()[:60]}")
    assert not offenders, "\n".join(offenders)


def test_print_only_in_entrypoints_and_scripts() -> None:
    """الإخراج للمشغّل بـprint محصور في نقاط الدخول؛ الباقي يمرّ عبر logging."""
    offenders = []
    for path in _files():
        if _rel(path).startswith(PRINT_ALLOWED):
            continue
        tree, _ = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, "\n".join(offenders)


#: تعابير f-string مسموحة داخل SQL، كلٌّ منها روجع يدوياً: قيمته من قوائم/ثوابت في الكود لا من المستخدم
REVIEWED_SQL_EXPRESSIONS = {
    "int(self._busy_timeout_ms)",   # عدد صحيح من الإعداد (PRAGMA لا يقبل معاملات)
    "id_column",                    # اسم عمود ثابت يمرّره المستودع الداخلي
    "column",                       # يُختار من قاموس/شرط ثابت (sent_count … أو is_read_by_*)
    "self._CALL_SELECT",            # ثابت صنف
}
#: أنماط مسموحة بالاسم (قوائم علامات ? وشروط وأعمدة تُبنى من الكود)
SAFE_SQL_NAME = re.compile(r"(marks|placeholders|where|clause|columns|assignments|set_sql|order|conditions|table|filters)", re.I)


def test_sql_fstrings_never_interpolate_user_values() -> None:
    """f-string داخل استدعاء SQL لا يُدخل إلا تعابير روجعت يدوياً (قيم المستخدم عبر معاملات ? فقط)."""
    sql_methods = {"execute", "fetchone", "fetchall", "fetchval", "executemany", "scalar"}
    offenders = []
    for path in _files():
        tree, _ = _parse(path)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in sql_methods
                and node.args
                and isinstance(node.args[0], ast.JoinedStr)
            ):
                continue
            for part in node.args[0].values:
                if not isinstance(part, ast.FormattedValue):
                    continue
                expr = ast.unparse(part.value)
                reviewed = expr in REVIEWED_SQL_EXPRESSIONS or SAFE_SQL_NAME.search(expr) or ".join(" in expr
                if not reviewed:
                    offenders.append(f"{_rel(path)}:{node.lineno} {{{expr}}}")
    assert not offenders, "قيمة غير مُراجَعة داخل SQL:\n" + "\n".join(offenders)
```

## `tests/integration/test_migrations.py` (مُحدَّث — مقتطف: الدوال المتغيرة كاملة)

استبدال `pytest.raises(Exception)` الأعمى بـ`MigrationError`.

```python
async def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    """فشل ترحيل في منتصفه لا يترك أثراً جزئياً في قاعدة البيانات."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_bad.sql").write_text(
        "CREATE TABLE good (id INTEGER PRIMARY KEY);\nCREATE TABLE bad (id INTEGER PRIMARY KEY;",
        encoding="utf-8",
    )
    database = Database(tmp_path / "bad.db")
    await database.connect()
    try:
        migrator = Migrator(database, migrations)
        with pytest.raises(MigrationError):
            await migrator.apply_all()
        tables = await database.table_names()
        assert "good" not in tables  # تراجع كامل
        assert await migrator.applied() == {}
    finally:
        await database.close()
```
