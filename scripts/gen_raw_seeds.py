"""가상 쇼핑몰의 raw data를 seeds/raw/*.csv로 만든다(값은 모두 지어낸 것이고, seed를 고정해 늘 같은 파일이 나온다).

실행: python scripts/gen_raw_seeds.py   (저장소 루트에서)
raw timestamp는 UTC다. staging model이 KST 일자로 바꾼다.
"""
from __future__ import annotations

import csv
import hashlib
import random
from datetime import date, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "seeds" / "raw"
START, END = date(2026, 9, 1), date(2026, 11, 17)      # 활동이 있는 기간(UTC 날짜)
R = random.Random(7)


def ts(day: date, hour=None) -> str:
    h = R.randrange(24) if hour is None else hour
    return datetime(day.year, day.month, day.day, h, R.randrange(60), R.randrange(60)).strftime("%Y-%m-%d %H:%M:%S")


def days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def write(name: str, header: list, rows: list) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{name}.csv {len(rows)} rows")


def main() -> None:
    # 회원: 6월부터 가입이 이어진다. 몇 명은 탈퇴했다.
    members = []
    for i in range(1, 121):
        joined = date(2026, 6, 1) + timedelta(days=R.randrange(0, 165))
        members.append({"id": i, "login_id": f"member{i:03d}", "joined": joined, "deleted": R.random() < 0.05})
    write("raw_members", ["id", "login_id", "created_at", "deleted_yn"],
          [[m["id"], m["login_id"], ts(m["joined"]), "Y" if m["deleted"] else "N"] for m in members])

    # 판매자 10곳, 상점 14개. 판매자 10은 내부 테스트 판매자다(seeds/ref/internal_seller_ids.csv). 상점 14는 닫았다.
    store_seller = {1: 1, 2: 1, 3: 2, 4: 3, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 11: 9, 12: 9, 13: 10, 14: 2}
    write("raw_stores", ["id", "seller_id", "opened_at", "closed_yn"],
          [[s, store_seller[s], ts(date(2026, 3, 1) + timedelta(days=s * 9)), "Y" if s == 14 else "N"] for s in store_seller])
    open_stores = [s for s in store_seller if s != 14]
    weights = [9, 7, 8, 6, 5, 6, 4, 3, 2, 2, 1, 1, 3]          # 상점마다 주문이 몰리는 정도

    # 입점 플랜: 끝난 플랜과 ENTERPRISE가 섞여 있다.
    plans = [(1, "PLUS", "2026-01-01", "2027-01-01"), (2, "BASIC", "2026-02-01", "2026-11-10"),
             (3, "ENTERPRISE", "2026-01-01", "2027-01-01"), (4, "BASIC", "2026-05-01", "2027-05-01"),
             (5, "PLUS", "2026-06-15", "2026-10-15"), (5, "BASIC", "2026-10-15", "2027-04-15"),
             (6, "BASIC", "2026-09-10", "2027-03-10"), (7, "ENTERPRISE", "2026-07-01", "2027-07-01"),
             (8, "BASIC", "2026-03-01", "2026-09-20"), (9, "PLUS", "2026-11-01", "2027-11-01")]
    write("raw_seller_plans", ["seller_id", "plan_code", "start_date", "end_date"], [list(p) for p in plans])

    logins, orders, cancels, refunds, checkout, search, tickets = [], [], [], [], [], [], []
    order_id = ticket_id = session_no = 0
    paths = ["/search", "/search", "/search", "/category", "/category/list", "/search/filter", "/product/detail"]
    for d in days(START, END):
        alive = [m for m in members if m["joined"] <= d and not (m["deleted"] and d > m["joined"] + timedelta(days=40))]
        weekend = d.weekday() >= 5
        for m in alive:                                   # 로그인: 주말에 조금 더 온다
            if R.random() < (0.30 if weekend else 0.22):
                for _ in range(1 if R.random() < 0.7 else 2):
                    logins.append([m["id"], ts(d)])
        for _ in range(R.randrange(7, 14) + (3 if weekend else 0)):      # 주문
            if not alive:
                break
            order_id += 1
            m, store, ordered = R.choice(alive), R.choices(open_stores, weights)[0], ts(d)
            delivered = d + timedelta(days=R.choice([1, 1, 2, 2, 2, 3, 3, 4, 6]))
            orders.append([order_id, m["id"], store, ordered, ts(delivered) if delivered <= END else "",
                           R.randrange(5, 120) * 1000, R.choice(["CARD", "CARD", "CARD", "EASYPAY", "EASYPAY", "BANK", "POINT"])])
            if R.random() < 0.07:                         # 취소. 절반쯤은 환불까지 간다
                cday = d + timedelta(days=R.randrange(0, 3))
                if cday <= END:
                    cancels.append([order_id, ts(cday)])
                    if R.random() < 0.55:
                        refunds.append([order_id, ts(cday), orders[-1][5]])
        for _ in range(R.randrange(9, 16)):               # 결제 퍼널: 세션마다 도달한 단계까지 이벤트가 남는다
            session_no += 1
            store, device = R.choices(open_stores, weights)[0], R.choice(["APP", "APP", "MOBILE_WEB", "PC_WEB"])
            reached, hour = R.choices([1, 2, 3, 4], [30, 25, 15, 30])[0], R.randrange(24)
            for step in range(1, reached + 1):
                checkout.append([f"s{session_no:05d}", store, device, step, ts(d, hour), 0])
                if R.random() < 0.12:
                    checkout.append([f"s{session_no:05d}", store, device, step, ts(d, hour), 1])
        for _ in range(R.randrange(22, 36)):              # 상점 내 검색 로그. user_key는 로그인 id의 hash다
            if not alive:
                break
            m = R.choice(alive)
            search.append([ts(d), R.choices(open_stores, weights)[0],
                           hashlib.md5(m["login_id"].encode()).hexdigest()[:16], R.choice(paths)])
        if R.random() < 0.8:                              # 고객문의
            ticket_id += 1
            tickets.append([ticket_id, R.randrange(1, 11), ts(d)])

    write("raw_login_history", ["member_id", "created_at"], logins)
    write("raw_orders", ["id", "member_id", "store_id", "ordered_at", "delivered_at", "total_amount", "pay_method"], orders)
    write("raw_order_cancels", ["order_id", "canceled_at"], cancels)
    write("raw_refunds", ["order_id", "refunded_at", "refund_amount"], refunds)
    write("raw_checkout_events", ["session_id", "store_id", "device_type", "step_no", "event_at", "is_retry"], checkout)
    write("raw_search_logs", ["logged_at", "store_id", "user_key", "path"], search)
    write("raw_cs_tickets", ["id", "seller_id", "created_at"], tickets)

    follows = set()
    while len(follows) < 160:
        follows.add((R.randrange(1, 121), R.randrange(1, 11)))
    write("raw_seller_follows", ["member_id", "seller_id", "followed_at", "unfollowed_at"],
          [[m, s, ts(date(2026, 8, 1) + timedelta(days=R.randrange(0, 100))), ""] for m, s in sorted(follows)])


if __name__ == "__main__":
    main()
