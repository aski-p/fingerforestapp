"""FingerForest 사용자끼리 대화: 친구 · 대화방(1:1·그룹) · 쪽지.

사람은 신 포레스트 직원 id(숫자 문자열)로 식별한다(owner_key "forest:133" → "133").
저장소는 두 가지: 운영은 Supabase(PostgREST) 테이블, 로컬·테스트는 SQLite.
테이블은 supabase_social_schema.sql 로 만든다.
"""
import datetime as dt
import json
import sqlite3
import threading
import urllib.parse

MAX_BODY = 2000
MAX_GROUP = 30


class SocialError(RuntimeError):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _clean_body(body):
    text = str(body or "").strip()
    if not text:
        raise SocialError("내용을 입력해 주세요.")
    if len(text) > MAX_BODY:
        raise SocialError(f"메시지는 {MAX_BODY}자까지 보낼 수 있어요.")
    return text


def _clean_id(value):
    text = str(value or "").strip()
    if not text.isdigit():
        raise SocialError("직원을 다시 선택해 주세요.")
    return text


# ---------------------------------------------------------------- stores
class SqliteStore:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(
                """
                create table if not exists fruit_friends (owner text, friend text, friend_name text, status text, requested_by text, updated_at text, primary key (owner, friend));
                create table if not exists fruit_rooms (id integer primary key autoincrement, kind text, title text, dm_key text unique, created_by text, created_at text, last_message_at text);
                create table if not exists fruit_room_members (room_id integer, member text, member_name text, last_read_id integer default 0, joined_at text, primary key (room_id, member));
                create table if not exists fruit_messages (id integer primary key autoincrement, room_id integer, sender text, sender_name text, body text, created_at text);
                create table if not exists fruit_notes (id integer primary key autoincrement, sender text, sender_name text, recipient text, recipient_name text, body text, read_at text, created_at text);
                """
            )

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def select(self, table, where=None, order=None, limit=None):
        sql, args = f"select * from {table}", []
        if where:
            parts = []
            for key, value in where.items():
                if isinstance(value, (list, tuple, set)):
                    values = list(value)
                    if not values:
                        return []
                    parts.append(f"{key} in ({','.join('?' * len(values))})")
                    args += values
                elif value is None:
                    parts.append(f"{key} is null")
                elif key.endswith("__gt"):
                    parts.append(f"{key[:-4]} > ?")
                    args.append(value)
                else:
                    parts.append(f"{key} = ?")
                    args.append(value)
            sql += " where " + " and ".join(parts)
        if order:
            column, _, direction = order.partition(".")
            sql += f" order by {column} {'desc' if direction == 'desc' else 'asc'}"
        if limit:
            sql += f" limit {int(limit)}"
        with self.lock, self._conn() as c:
            return [dict(row) for row in c.execute(sql, args).fetchall()]

    def insert(self, table, row):
        keys = list(row)
        with self.lock, self._conn() as c:
            cur = c.execute(f"insert into {table} ({','.join(keys)}) values ({','.join('?' * len(keys))})", [row[k] for k in keys])
            new_id = cur.lastrowid
        rows = self.select(table, {"rowid": new_id}) if table in ("fruit_rooms", "fruit_messages", "fruit_notes") else [row]
        return rows[0] if rows else row

    def upsert(self, table, row, keys):
        cols = list(row)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in keys)
        with self.lock, self._conn() as c:
            c.execute(
                f"insert into {table} ({','.join(cols)}) values ({','.join('?' * len(cols))}) on conflict ({','.join(keys)}) do update set {updates}",
                [row[k] for k in cols],
            )

    def update(self, table, where, values):
        sets = ",".join(f"{k}=?" for k in values)
        conds = " and ".join(f"{k}=?" for k in where)
        with self.lock, self._conn() as c:
            c.execute(f"update {table} set {sets} where {conds}", list(values.values()) + list(where.values()))

    def delete(self, table, where):
        conds = " and ".join(f"{k}=?" for k in where)
        with self.lock, self._conn() as c:
            c.execute(f"delete from {table} where {conds}", list(where.values()))


class SupabaseStore:
    """PostgREST. request(method, path, body=None, extra_headers=None) 는 web_server.supabase_request."""

    def __init__(self, request):
        self.request = request

    @staticmethod
    def _filters(where):
        parts = []
        for key, value in (where or {}).items():
            if isinstance(value, (list, tuple, set)):
                values = ",".join(urllib.parse.quote(str(v), safe="") for v in value)
                parts.append(f"{key}=in.({values})")
            elif value is None:
                parts.append(f"{key}=is.null")
            elif key.endswith("__gt"):
                parts.append(f"{key[:-4]}=gt.{urllib.parse.quote(str(value), safe='')}")
            else:
                parts.append(f"{key}=eq.{urllib.parse.quote(str(value), safe='')}")
        return parts

    def select(self, table, where=None, order=None, limit=None):
        if where and any(isinstance(v, (list, tuple, set)) and not v for v in where.values()):
            return []
        q = ["select=*"] + self._filters(where)
        if order:
            q.append(f"order={order}")
        if limit:
            q.append(f"limit={int(limit)}")
        return self.request("GET", f"/rest/v1/{table}?{'&'.join(q)}") or []

    def insert(self, table, row):
        out = self.request("POST", f"/rest/v1/{table}", body=row, extra_headers={"Prefer": "return=representation"})
        return (out or [row])[0]

    def upsert(self, table, row, keys):
        self.request(
            "POST",
            f"/rest/v1/{table}?on_conflict={','.join(keys)}",
            body=row,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    def update(self, table, where, values):
        self.request("PATCH", f"/rest/v1/{table}?{'&'.join(self._filters(where))}", body=values, extra_headers={"Prefer": "return=minimal"})

    def delete(self, table, where):
        self.request("DELETE", f"/rest/v1/{table}?{'&'.join(self._filters(where))}", extra_headers={"Prefer": "return=minimal"})


# ---------------------------------------------------------------- service
class Social:
    def __init__(self, store):
        self.store = store

    # 친구 ---------------------------------------------------------
    def friends(self, me):
        rows = self.store.select("fruit_friends", {"owner": me})
        return {
            "friends": [r for r in rows if r["status"] == "accepted"],
            "incoming": [r for r in rows if r["status"] == "pending" and r["requested_by"] != me],
            "outgoing": [r for r in rows if r["status"] == "pending" and r["requested_by"] == me],
            "blocked": [r for r in rows if r["status"] == "blocked"],
        }

    def _relation(self, a, b):
        rows = self.store.select("fruit_friends", {"owner": a, "friend": b})
        return rows[0] if rows else None

    def request_friend(self, me, me_name, other, other_name):
        other = _clean_id(other)
        if other == me:
            raise SocialError("나에게는 친구 신청을 할 수 없어요.")
        theirs = self._relation(other, me)
        if theirs and theirs["status"] == "blocked":
            raise SocialError("친구 신청을 보낼 수 없어요.")
        mine = self._relation(me, other)
        if mine and mine["status"] == "accepted":
            return "already"
        if theirs and theirs["status"] == "pending" and theirs["requested_by"] == other:
            return self.respond_friend(me, me_name, other, True)
        now = _now()
        self.store.upsert("fruit_friends", {"owner": me, "friend": other, "friend_name": other_name or "", "status": "pending", "requested_by": me, "updated_at": now}, ["owner", "friend"])
        self.store.upsert("fruit_friends", {"owner": other, "friend": me, "friend_name": me_name or "", "status": "pending", "requested_by": me, "updated_at": now}, ["owner", "friend"])
        return "requested"

    def respond_friend(self, me, me_name, other, accept):
        other = _clean_id(other)
        mine = self._relation(me, other)
        if not mine or mine["status"] != "pending":
            raise SocialError("받은 친구 신청이 없어요.")
        if not accept:
            self.store.delete("fruit_friends", {"owner": me, "friend": other})
            self.store.delete("fruit_friends", {"owner": other, "friend": me})
            return "declined"
        now = _now()
        self.store.update("fruit_friends", {"owner": me, "friend": other}, {"status": "accepted", "updated_at": now})
        self.store.update("fruit_friends", {"owner": other, "friend": me}, {"status": "accepted", "friend_name": me_name or "", "updated_at": now})
        return "accepted"

    def remove_friend(self, me, other):
        other = _clean_id(other)
        self.store.delete("fruit_friends", {"owner": me, "friend": other})
        self.store.delete("fruit_friends", {"owner": other, "friend": me})
        return "removed"

    def block(self, me, other, other_name=""):
        other = _clean_id(other)
        self.store.delete("fruit_friends", {"owner": other, "friend": me})
        self.store.upsert("fruit_friends", {"owner": me, "friend": other, "friend_name": other_name or "", "status": "blocked", "requested_by": me, "updated_at": _now()}, ["owner", "friend"])
        return "blocked"

    def _blocked_by(self, member, me):
        rel = self._relation(member, me)
        return bool(rel and rel["status"] == "blocked")

    # 대화방 -------------------------------------------------------
    def open_room(self, me, me_name, members, title=""):
        """members: [{"id","name"}]. 2명이면 1:1(같은 두 사람이면 기존 방), 3명 이상이면 그룹방."""
        others = {}
        for m in members or []:
            mid = _clean_id(m.get("id"))
            if mid != me:
                others[mid] = str(m.get("name") or "")
        if not others:
            raise SocialError("대화할 사람을 골라 주세요.")
        if len(others) + 1 > MAX_GROUP:
            raise SocialError(f"그룹 대화는 {MAX_GROUP}명까지예요.")
        for mid in others:
            if self._blocked_by(mid, me):
                raise SocialError("이 사람과는 대화를 시작할 수 없어요.")
        now = _now()
        if len(others) == 1:
            other = next(iter(others))
            dm_key = ":".join(sorted([me, other], key=int))
            existing = self.store.select("fruit_rooms", {"dm_key": dm_key})
            if existing:
                return existing[0]
            room = self.store.insert("fruit_rooms", {"kind": "dm", "title": "", "dm_key": dm_key, "created_by": me, "created_at": now, "last_message_at": now})
        else:
            room = self.store.insert("fruit_rooms", {"kind": "group", "title": str(title or "")[:60], "dm_key": None, "created_by": me, "created_at": now, "last_message_at": now})
        rid = room["id"]
        self.store.upsert("fruit_room_members", {"room_id": rid, "member": me, "member_name": me_name or "", "last_read_id": 0, "joined_at": now}, ["room_id", "member"])
        for mid, name in others.items():
            self.store.upsert("fruit_room_members", {"room_id": rid, "member": mid, "member_name": name, "last_read_id": 0, "joined_at": now}, ["room_id", "member"])
        return room

    def _membership(self, me, room_id):
        rows = self.store.select("fruit_room_members", {"room_id": int(room_id), "member": me})
        if not rows:
            raise SocialError("이 대화방에 들어가 있지 않아요.")
        return rows[0]

    def rooms(self, me):
        memberships = self.store.select("fruit_room_members", {"member": me})
        if not memberships:
            return []
        ids = [m["room_id"] for m in memberships]
        rooms = {r["id"]: r for r in self.store.select("fruit_rooms", {"id": ids})}
        everyone = self.store.select("fruit_room_members", {"room_id": ids})
        out = []
        for m in memberships:
            room = rooms.get(m["room_id"])
            if not room:
                continue
            last = self.store.select("fruit_messages", {"room_id": room["id"]}, order="id.desc", limit=1)
            unread = self.store.select("fruit_messages", {"room_id": room["id"], "id__gt": int(m.get("last_read_id") or 0)})
            unread = [x for x in unread if x["sender"] != me]
            members = [{"id": x["member"], "name": x.get("member_name") or ""} for x in everyone if x["room_id"] == room["id"]]
            names = [x["name"] for x in members if x["id"] != me]
            out.append({
                "id": room["id"],
                "kind": room["kind"],
                "title": room.get("title") or ", ".join(n for n in names if n) or "대화",
                "members": members,
                "lastMessage": (last[0]["body"][:80] if last else ""),
                "lastAt": (last[0]["created_at"] if last else room.get("created_at")),
                "unread": len(unread),
            })
        out.sort(key=lambda r: r["lastAt"] or "", reverse=True)
        return out

    def messages(self, me, room_id, after=0, limit=60):
        self._membership(me, room_id)
        rows = self.store.select("fruit_messages", {"room_id": int(room_id), "id__gt": int(after or 0)}, order="id.asc", limit=limit if after else None)
        if not after:
            rows = rows[-limit:]
        return [{"id": r["id"], "sender": r["sender"], "senderName": r.get("sender_name") or "", "body": r["body"], "at": r["created_at"], "mine": r["sender"] == me} for r in rows]

    def send(self, me, me_name, room_id, body):
        membership = self._membership(me, room_id)
        text = _clean_body(body)
        members = self.store.select("fruit_room_members", {"room_id": int(room_id)})
        if any(m["member"] != me and self._blocked_by(m["member"], me) for m in members) and len(members) == 2:
            raise SocialError("상대가 대화를 받지 않아요.")
        now = _now()
        row = self.store.insert("fruit_messages", {"room_id": int(room_id), "sender": me, "sender_name": me_name or "", "body": text, "created_at": now})
        self.store.update("fruit_rooms", {"id": int(room_id)}, {"last_message_at": now})
        self.store.update("fruit_room_members", {"room_id": int(room_id), "member": me}, {"last_read_id": int(row.get("id") or membership.get("last_read_id") or 0)})
        return {"id": row.get("id"), "recipients": [m["member"] for m in members if m["member"] != me]}

    def mark_read(self, me, room_id, last_id):
        membership = self._membership(me, room_id)
        if int(last_id or 0) > int(membership.get("last_read_id") or 0):
            self.store.update("fruit_room_members", {"room_id": int(room_id), "member": me}, {"last_read_id": int(last_id)})
        return "ok"

    def leave(self, me, room_id):
        self._membership(me, room_id)
        self.store.delete("fruit_room_members", {"room_id": int(room_id), "member": me})
        return "left"

    # 쪽지 ---------------------------------------------------------
    def send_note(self, me, me_name, to, to_name, body):
        to = _clean_id(to)
        if to == me:
            raise SocialError("나에게는 쪽지를 보낼 수 없어요.")
        if self._blocked_by(to, me):
            raise SocialError("쪽지를 보낼 수 없어요.")
        row = self.store.insert("fruit_notes", {"sender": me, "sender_name": me_name or "", "recipient": to, "recipient_name": to_name or "", "body": _clean_body(body), "read_at": None, "created_at": _now()})
        return {"id": row.get("id")}

    def notes(self, me, limit=50):
        inbox = self.store.select("fruit_notes", {"recipient": me}, order="id.desc", limit=limit)
        sent = self.store.select("fruit_notes", {"sender": me}, order="id.desc", limit=limit)
        fmt = lambda r: {"id": r["id"], "from": r["sender"], "fromName": r.get("sender_name") or "", "to": r["recipient"], "toName": r.get("recipient_name") or "", "body": r["body"], "at": r["created_at"], "read": bool(r.get("read_at"))}
        return {"inbox": [fmt(r) for r in inbox], "sent": [fmt(r) for r in sent]}

    def read_note(self, me, note_id):
        rows = self.store.select("fruit_notes", {"id": int(note_id), "recipient": me})
        if not rows:
            raise SocialError("쪽지를 찾지 못했어요.")
        if not rows[0].get("read_at"):
            self.store.update("fruit_notes", {"id": int(note_id)}, {"read_at": _now()})
        return "ok"

    # 요약 ---------------------------------------------------------
    def summary(self, me):
        f = self.friends(me)
        rooms = self.rooms(me)
        unread_notes = len(self.store.select("fruit_notes", {"recipient": me, "read_at": None}))
        return {
            **f,
            "rooms": rooms,
            "unreadMessages": sum(r["unread"] for r in rooms),
            "unreadNotes": unread_notes,
            "pendingRequests": len(f["incoming"]),
        }


class SupabaseDocStore:
    """새 테이블 없이 기존 fruit_chat_messages 테이블에 문서처럼 저장한다.
    한 레코드 = 한 행: user_key='social:<table>', model=<table>, metadata=레코드(JSON). 자동 증가 id는 행 id를 쓴다."""

    TABLE = "fruit_chat_messages"
    SERIAL = {"fruit_rooms", "fruit_messages", "fruit_notes"}

    def __init__(self, request):
        self.request = request

    def _filters(self, table, where):
        parts = [f"user_key=eq.{urllib.parse.quote('social:' + table, safe='')}"]
        for key, value in (where or {}).items():
            gt = key.endswith("__gt")
            field = key[:-4] if gt else key
            column = "id" if (field in ("id", "rowid") and table in self.SERIAL) else f"metadata->>{field}"
            if isinstance(value, (list, tuple, set)):
                values = ",".join(urllib.parse.quote(str(v), safe="") for v in value)
                parts.append(f"{column}=in.({values})")
            elif value is None:
                parts.append(f"{column}=is.null")
            elif gt:
                # metadata 숫자 비교는 문자열 비교가 되므로 id(행 번호)에만 쓴다
                parts.append(f"{column}=gt.{int(value)}")
            else:
                parts.append(f"{column}=eq.{urllib.parse.quote(str(value), safe='')}")
        return parts

    def _record(self, table, row):
        record = dict(row.get("metadata") or {})
        if table in self.SERIAL:
            record["id"] = row["id"]
        record["_row"] = row["id"]
        return record

    def select(self, table, where=None, order=None, limit=None):
        if where and any(isinstance(v, (list, tuple, set)) and not v for v in where.values()):
            return []
        q = ["select=id,metadata"] + self._filters(table, where)
        q.append(f"order={order or 'id.asc'}")
        if limit:
            q.append(f"limit={int(limit)}")
        rows = self.request("GET", f"/rest/v1/{self.TABLE}?{'&'.join(q)}") or []
        out = [self._record(table, r) for r in rows]
        for r in out:
            r.pop("_row", None)
        return out

    def _rows(self, table, where):
        q = ["select=id,metadata"] + self._filters(table, where)
        return self.request("GET", f"/rest/v1/{self.TABLE}?{'&'.join(q)}") or []

    def insert(self, table, row):
        clean = {k: v for k, v in row.items() if k != "id"}
        out = self.request(
            "POST", f"/rest/v1/{self.TABLE}",
            body={"user_key": f"social:{table}", "role": "user", "content": "-", "model": table, "metadata": clean},
            extra_headers={"Prefer": "return=representation"},
        )
        created = (out or [{}])[0]
        record = dict(clean)
        if table in self.SERIAL:
            record["id"] = created.get("id")
        return record

    def upsert(self, table, row, keys):
        existing = self._rows(table, {k: row[k] for k in keys})
        if existing:
            merged = {**(existing[0].get("metadata") or {}), **row}
            self.request("PATCH", f"/rest/v1/{self.TABLE}?id=eq.{existing[0]['id']}", body={"metadata": merged}, extra_headers={"Prefer": "return=minimal"})
            for extra in existing[1:]:
                self.request("DELETE", f"/rest/v1/{self.TABLE}?id=eq.{extra['id']}", extra_headers={"Prefer": "return=minimal"})
        else:
            self.insert(table, row)

    def update(self, table, where, values):
        for r in self._rows(table, where):
            merged = {**(r.get("metadata") or {}), **values}
            self.request("PATCH", f"/rest/v1/{self.TABLE}?id=eq.{r['id']}", body={"metadata": merged}, extra_headers={"Prefer": "return=minimal"})

    def delete(self, table, where):
        for r in self._rows(table, where):
            self.request("DELETE", f"/rest/v1/{self.TABLE}?id=eq.{r['id']}", extra_headers={"Prefer": "return=minimal"})
