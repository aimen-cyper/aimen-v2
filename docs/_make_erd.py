"""رسم مخطط ERD لقاعدة بيانات نظام SMM Bot (مرحلة التصميم فقط)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

GROUPS = {
    "rbac":    ("#e8effb", "#2f5597", "Users / RBAC"),
    "catalog": ("#e6f5ea", "#2e7d32", "Providers / Catalog"),
    "orders":  ("#fdf0e2", "#b45f06", "Orders / Money"),
    "pay":     ("#f3e9fb", "#6a3b9a", "Payments"),
    "support": ("#e3f5f6", "#0f7b86", "Support"),
    "sys":     ("#eeeeee", "#555555", "System / Logs"),
}

# (key, title, group, [columns])
COLUMNS = [
    [  # column 0
        ("roles", "roles", "rbac", ["code  PK", "name_ar", "level"]),
        ("permissions", "permissions", "rbac", ["code  PK", "name_ar", "group"]),
        ("role_permissions", "role_permissions", "rbac", ["role_code  FK", "permission_code  FK"]),
        ("user_permissions", "user_permissions", "rbac", ["user_id  FK", "permission_code  FK", "allow"]),
        ("settings", "settings", "sys", ["key  PK", "value", "value_type", "updated_by"]),
        ("schema_migrations", "schema_migrations", "sys", ["version  PK", "applied_at"]),
        ("idempotency_keys", "idempotency_keys", "sys", ["key  PK", "scope", "expires_at"]),
        ("backups", "backups", "sys", ["id  PK", "filename", "sha256"]),
        ("error_logs", "error_logs", "sys", ["id  PK", "level / source", "message"]),
    ],
    [  # column 1
        ("users", "users", "rbac", ["id  PK", "telegram_id  U", "username", "balance_units", "role  FK", "is_banned", "language", "last_activity"]),
        ("user_states", "user_states", "sys", ["user_id  PK", "state", "data_json", "expires_at"]),
        ("providers", "providers", "catalog", ["id  PK", "name  U", "api_url", "api_key_enc", "api_type", "balance_units", "is_active"]),
        ("service_categories", "service_categories", "catalog", ["id  PK", "name_ar", "emoji", "sort_order"]),
        ("payment_methods", "payment_methods", "pay", ["id  PK", "code  U", "type", "instructions_ar", "is_active"]),
        ("broadcasts", "broadcasts", "sys", ["id  PK", "admin_id  FK", "target", "sent/failed", "status"]),
    ],
    [  # column 2
        ("services", "services", "catalog", ["id  PK", "category_id  FK", "provider_id  FK", "provider_service_id", "price_per_1000_units", "provider_price_units", "min_qty / max_qty", "is_active / is_archived"]),
        ("orders", "orders", "orders", ["id  PK", "user_id  FK", "service_id  FK", "provider_id  FK", "link / quantity", "cost_units", "status", "provider_order_id  U", "client_request_id  U", "refund_amount_units", "locked_until / next_check_at"]),
        ("payments", "payments", "pay", ["id  PK", "user_id  FK", "method_id  FK", "amount_units", "status", "proof_file_id", "admin_id  FK", "expires_at"]),
        ("support_tickets", "support_tickets", "support", ["id  PK", "user_id  FK", "subject", "status", "assigned_admin  FK"]),
        ("notifications", "notifications", "sys", ["id  PK", "user_id  FK", "type", "dedupe_key  U", "status / attempts"]),
    ],
    [  # column 3
        ("service_price_history", "service_price_history", "catalog", ["id  PK", "service_id  FK", "old/new price", "changed_by"]),
        ("order_status_history", "order_status_history", "orders", ["id  PK", "order_id  FK", "from / to status", "actor_type", "reason"]),
        ("transactions", "transactions", "orders", ["id  PK", "user_id  FK", "order_id  FK", "payment_id  FK", "type / direction", "amount_units", "balance_before/after", "reference  U"]),
        ("support_messages", "support_messages", "support", ["id  PK", "ticket_id  FK", "sender_id  FK", "sender_type", "message"]),
        ("broadcast_recipients", "broadcast_recipients", "sys", ["id  PK", "broadcast_id  FK", "user_id  FK", "status"]),
        ("provider_requests", "provider_requests", "catalog", ["id  PK", "provider_id  FK", "order_id  FK", "action / http_status"]),
        ("audit_logs", "audit_logs", "sys", ["id  PK", "admin_id  FK", "action", "target_type / id", "before/after_json"]),
    ],
]

# (src, dst, label)
RELATIONS = [
    ("roles", "users", "1:N"),
    ("roles", "role_permissions", "1:N"),
    ("permissions", "role_permissions", "1:N"),
    ("permissions", "user_permissions", "1:N"),
    ("users", "user_permissions", "1:N"),
    ("users", "orders", "1:N"),
    ("users", "payments", "1:N"),
    ("users", "support_tickets", "1:N"),
    ("users", "notifications", "1:N"),
    ("users", "transactions", "1:N"),
    ("users", "audit_logs", "1:N"),
    ("users", "user_states", "1:1"),
    ("providers", "services", "1:N"),
    ("providers", "orders", "1:N"),
    ("providers", "provider_requests", "1:N"),
    ("service_categories", "services", "1:N"),
    ("services", "orders", "1:N"),
    ("services", "service_price_history", "1:N"),
    ("orders", "order_status_history", "1:N"),
    ("orders", "transactions", "1:N"),
    ("payments", "transactions", "1:N"),
    ("payment_methods", "payments", "1:N"),
    ("support_tickets", "support_messages", "1:N"),
    ("broadcasts", "broadcast_recipients", "1:N"),
]

COL_X = [3, 45, 90, 148]
COL_W = [36, 39, 50, 40]
TOP = 145.0
GAP = 2.3
LINE_H = 2.35
HEAD_H = 4.6
PAD = 1.6

boxes = {}
for ci, col in enumerate(COLUMNS):
    y = TOP
    for key, title, group, cols in col:
        h = HEAD_H + LINE_H * len(cols) + PAD
        boxes[key] = dict(x=COL_X[ci], y=y - h, w=COL_W[ci], h=h, title=title,
                          group=group, cols=cols, col=ci)
        y -= h + GAP

fig, ax = plt.subplots(figsize=(21.5, 16.0), dpi=105)
ax.set_xlim(0, 192)
ax.set_ylim(0, 150)
ax.axis("off")
ax.set_facecolor("white")

# ---- الصناديق ----
for key, b in boxes.items():
    fill, edge, _ = GROUPS[b["group"]]
    ax.add_patch(FancyBboxPatch((b["x"], b["y"]), b["w"], b["h"],
                                boxstyle="round,pad=0,rounding_size=0.8",
                                linewidth=1.4, edgecolor=edge, facecolor="white", zorder=3))
    ax.add_patch(Rectangle((b["x"], b["y"] + b["h"] - HEAD_H), b["w"], HEAD_H,
                           linewidth=0, facecolor=edge, zorder=4))
    ax.text(b["x"] + b["w"] / 2, b["y"] + b["h"] - HEAD_H / 2, b["title"],
            ha="center", va="center", fontsize=10.5, color="white",
            fontweight="bold", zorder=5, family="DejaVu Sans")
    ax.add_patch(Rectangle((b["x"], b["y"]), b["w"], b["h"] - HEAD_H,
                           linewidth=0, facecolor=fill, alpha=0.55, zorder=3.5))
    for i, c in enumerate(b["cols"]):
        ax.text(b["x"] + 1.4, b["y"] + b["h"] - HEAD_H - LINE_H * (i + 0.65), c,
                ha="left", va="center", fontsize=7.8, color="#222222", zorder=5,
                family="DejaVu Sans")

# ---- توزيع نقاط الارتساء على حواف الصناديق ----
out_anchors, in_anchors = {}, {}
for s, d, _ in RELATIONS:
    out_anchors.setdefault(s, []).append(d)
    in_anchors.setdefault(d, []).append(s)

def spread(box, n):
    """توزيع n نقطة عمودياً داخل ارتفاع الصندوق."""
    top = box["y"] + box["h"] - HEAD_H - 0.6
    bot = box["y"] + 0.9
    if n == 1:
        return [(top + bot) / 2]
    step = (top - bot) / (n - 1)
    return [top - step * i for i in range(n)]

out_pos = {k: dict(zip(v, spread(boxes[k], len(v)))) for k, v in out_anchors.items()}
in_pos = {k: dict(zip(v, spread(boxes[k], len(v)))) for k, v in in_anchors.items()}

lane = {}
for idx, (s, d, label) in enumerate(RELATIONS):
    sb, db = boxes[s], boxes[d]
    y1 = out_pos[s][d]
    y2 = in_pos[d][s]
    edge_color = GROUPS[sb["group"]][1]
    if sb["col"] < db["col"]:
        x1 = sb["x"] + sb["w"]
        x2 = db["x"]
        if db["col"] - sb["col"] >= 2:
            # قفزة طويلة: تمر عبر ممر سفلي فارغ لتفادي عبور الصناديق
            lane["bottom"] = lane.get("bottom", 0) + 1
            yb = 9.0 - lane["bottom"] * 2.2
            path = [(x1, y1), (x1 + 2.0, y1), (x1 + 2.0, yb), (x2 - 3.0, yb),
                    (x2 - 3.0, y2), (x2, y2)]
        else:
            key = (sb["col"], db["col"])
            lane[key] = lane.get(key, 0) + 1
            xm = x1 + (x2 - x1) * 0.32 + (lane[key] % 6) * 1.05
            path = [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
    else:  # نفس العمود: التفاف من اليمين
        x1 = sb["x"] + sb["w"]
        x2 = db["x"] + db["w"]
        xm = max(x1, x2) + 2.0 + (idx % 3) * 1.0
        path = [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    ax.plot(xs, ys, color=edge_color, linewidth=1.15, alpha=0.85, zorder=2,
            solid_capstyle="round")
    ax.plot([xs[0]], [ys[0]], marker="o", markersize=2.8, color=edge_color, zorder=6)
    ax.annotate("", xy=(xs[-1], ys[-1]), xytext=(xs[-2] + (0.9 if xs[-1] > xs[-2] else -0.9), ys[-1]),
                arrowprops=dict(arrowstyle="-|>", color=edge_color, lw=1.15), zorder=6)
    ax.text(xs[0] + 0.9, ys[0] + 0.85, "1", fontsize=6.5, color=edge_color, zorder=6)
    ax.text(xs[-1] - 2.0 if xs[-1] > xs[-2] else xs[-1] + 1.2, ys[-1] + 0.85, "N",
            fontsize=6.5, color=edge_color, zorder=6)

# ---- العنوان والمفتاح ----
ax.text(3, 148.6, "SMM Telegram Bot  —  Database ERD  (Phase 0 Design)",
        fontsize=16, fontweight="bold", color="#1a1a1a", family="DejaVu Sans")
ax.text(3, 146.6, "PK = primary key   |   FK = foreign key   |   U = unique   |   *_units = integer money (1/10,000 of currency)   |   arrows: 1 --> N",
        fontsize=8.5, color="#555555", family="DejaVu Sans")

lx = 96
for gname, (fill, edge, label) in GROUPS.items():
    ax.add_patch(Rectangle((lx, 147.0), 2.4, 1.6, facecolor=edge, edgecolor=edge))
    ax.text(lx + 3.0, 147.8, label, fontsize=8.5, va="center", color="#333333",
            family="DejaVu Sans")
    lx += 17.5

plt.tight_layout()
fig.savefig("/home/user/smm_bot/docs/erd.png", dpi=105, bbox_inches="tight",
            facecolor="white")
print("saved")
