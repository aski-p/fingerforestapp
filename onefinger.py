"""새 OneFinger(신 포레스트) 연결 (2026-11-19).

옛 포레스트(forest2.fingerservice.co.kr/api/v1/dw)와 옛 PMS 로그인은 2026-11-16 새 OneFinger로 옮겨졌다.
앱에서 쓴 업무일지·열매 선물이 옛 포레스트로 들어가 신 포레스트에 반영되지 않던 문제를 이 모듈로 고친다.

 - 로그인: 브라우저와 같은 통합 로그인(OIDC) 흐름을 따라간다. 사번(숫자) + 비밀번호. 비밀번호는 HTTPS 폼으로만 보낸다.
 - API: {ONEFINGER_URL}/pms-api/...  응답 {data, meta} / 오류 {error:{code,message}}
 - 쓰기(POST/PUT): X-CSRF-Token(GET /auth/session) + Idempotency-Key + X-Forest-Expected-Employee-Id
명세는 새 OneFinger 웹 화면 스크립트에 들어 있는 API 정의(get_me, get_employees, get_me_reward_balance,
post_fruit_gifts, get/put_me_worklogs_date, get_me_reward_ledger, get_rankings, get_me_worklog_calendar)를 따른다.
"""
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

ONEFINGER_URL = os.environ.get("ONEFINGER_URL", "https://onefinger.fingerservice.co.kr").rstrip("/")
ONEFINGER_SSO_URL = os.environ.get("ONEFINGER_SSO_URL", "https://sso-onefinger.fingerservice.co.kr").rstrip("/")
API_PREFIX = "/pms-api"
TIMEOUT = 25


class OneFingerError(RuntimeError):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class LoginFailed(OneFingerError):
    pass


def _host(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def parse_login_form(html):
    form = re.search(r"<form[^>]*id=[\"']login-form[\"'][^>]*>", html, re.I) or re.search(r"<form[^>]*action=[\"']/login[\"'][^>]*>", html, re.I)
    if not form:
        return None
    action = re.search(r"action=[\"']([^\"']+)[\"']", form.group(0), re.I)
    inp = re.search(r"<input[^>]*name=[\"']csrf[\"'][^>]*>", html, re.I)
    csrf = re.search(r"value=[\"']([^\"']*)[\"']", inp.group(0), re.I) if inp else None
    if not csrf:
        return None
    return {"csrf": csrf.group(1).replace("&amp;", "&"), "action": (action.group(1) if action else "/login").replace("&amp;", "&")}


def login_error_text(html):
    m = re.search(r"<[a-z]+[^>]*(?:id=[\"']login-error[\"']|role=[\"']alert[\"'])[^>]*>([\s\S]*?)</[a-z]+>", html, re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""


def classify_login_failure(html, status):
    text = login_error_text(html)
    if re.search(r"잠금|잠겼|잠긴|locked", text, re.I):
        return "locked"
    if re.search(r"비밀번호[^.]{0,20}(변경해|만료)", text):
        return "must_change_password"
    if re.search(r"(사번|아이디|비밀번호)[^.]{0,30}(일치하지|올바르지|틀렸|확인해)|invalid", text, re.I) or status == 401:
        return "invalid_credentials"
    return "unknown"


class OneFingerClient:
    """한 사람의 OneFinger 세션(쿠키). 요청 하나 동안만 쓰고 쿠키는 저장하지 않는다."""

    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.employee = None  # /me 의 employee (id, employeeNo, name, organizationName, positionName)

    def _open(self, req, timeout=TIMEOUT):
        try:
            return self.opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            return exc  # 상태 코드와 본문을 호출한 쪽이 본다
        except urllib.error.URLError as exc:
            raise OneFingerError(f"OneFinger 연결 실패: {exc.reason}", code="NETWORK") from exc

    # ---------- 로그인 ----------
    def login(self, employee_no, password):
        employee_no = str(employee_no or "").strip()
        if not re.fullmatch(r"[1-9][0-9]{0,18}", employee_no):
            raise LoginFailed("새 OneFinger는 숫자 사번으로 로그인해요. 사번을 확인해 주세요.", code="SSO_EMPNO_FORMAT")
        start = f"{ONEFINGER_URL}/auth/login?return_to={urllib.parse.quote(ONEFINGER_URL + '/', safe='')}"
        res = self._open(urllib.request.Request(start, headers={"Accept": "text/html"}))
        page_url = res.geturl()
        html = res.read().decode("utf-8", "replace")
        if _host(page_url) != _host(ONEFINGER_SSO_URL):
            raise OneFingerError(f"통합 로그인 화면을 열지 못했어요({getattr(res, 'status', '?')}).", code="SSO_START")
        form = parse_login_form(html)
        if not form:
            raise OneFingerError("통합 로그인 화면 형식이 바뀌었어요.", code="SSO_NOFORM")
        post_url = urllib.parse.urljoin(page_url, form["action"])
        if _host(post_url) != _host(ONEFINGER_SSO_URL):
            raise OneFingerError("통합 로그인 주소가 올바르지 않아요.", code="SSO_FORM_ORIGIN")
        body = urllib.parse.urlencode({"csrf": form["csrf"], "employee_no": employee_no, "password": password}).encode()
        req = urllib.request.Request(post_url, data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": ONEFINGER_SSO_URL,
            "Referer": page_url,
            "Accept": "text/html",
        })
        end = self._open(req)
        end_url = end.geturl()
        if _host(end_url) == _host(ONEFINGER_SSO_URL):
            end_html = end.read().decode("utf-8", "replace")
            kind = classify_login_failure(end_html, getattr(end, "status", getattr(end, "code", 0)))
            messages = {
                "locked": "OneFinger 계정이 잠겼어요. 통합 로그인에서 잠금을 풀어 주세요.",
                "must_change_password": "OneFinger 비밀번호를 바꿔야 해요. 통합 로그인에서 변경한 뒤 다시 시도해 주세요.",
                "invalid_credentials": "사번 또는 비밀번호가 맞지 않아요. 새 OneFinger 비밀번호로 다시 로그인해 주세요.",
            }
            raise LoginFailed(messages.get(kind, "OneFinger 로그인에 실패했어요."), code=kind)
        s = self.session_info()
        if not s.get("authenticated"):
            raise OneFingerError("OneFinger 세션을 만들지 못했어요.", code="NO_SESSION")
        me = self.api("GET", "/me")
        emp = (me or {}).get("employee") or {}
        if not emp.get("id"):
            raise OneFingerError("OneFinger 직원 정보를 읽지 못했어요.", code="NO_ME")
        self.employee = emp
        return emp

    def session_info(self):
        res = self._open(urllib.request.Request(f"{ONEFINGER_URL}/auth/session", headers={"Accept": "application/json"}), timeout=10)
        if getattr(res, "status", getattr(res, "code", 0)) != 200:
            return {"authenticated": False}
        try:
            j = json.loads(res.read().decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError:
            return {"authenticated": False}
        return {"authenticated": j.get("authenticated") is not False and bool(j.get("csrf_token")), "csrf": j.get("csrf_token")}

    # ---------- API ----------
    def api(self, method, path, query=None, body=None, ok=(200, 201)):
        url = f"{ONEFINGER_URL}{'' if path.startswith('/api/') else API_PREFIX}{path}"
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None and v != ""})
        headers = {"Accept": "application/json"}
        data = None
        if method != "GET":
            s = self.session_info()
            if not s.get("authenticated"):
                raise OneFingerError("OneFinger 세션이 끝났어요. 다시 로그인해 주세요.", code="AUTH", status=401)
            headers["X-CSRF-Token"] = s["csrf"]
            headers["Idempotency-Key"] = str(uuid.uuid4())
            if self.employee and self.employee.get("id"):
                headers["X-Forest-Expected-Employee-Id"] = str(self.employee["id"])
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode()
        res = self._open(urllib.request.Request(url, data=data, method=method, headers=headers))
        status = getattr(res, "status", getattr(res, "code", 0))
        text = res.read().decode("utf-8", "replace")
        try:
            j = json.loads(text) if text else {}
        except json.JSONDecodeError:
            j = {}
        if status not in ok:
            err = (j.get("error") or {}) if isinstance(j, dict) else {}
            raise OneFingerError(f"OneFinger {method} {path} 실패({status}): {err.get('message') or err.get('code') or text[:200]}", code=err.get("code") or str(status), status=status)
        return j.get("data") if isinstance(j, dict) else None

    # ---------- 포레스트 ----------
    def employees(self):
        out, cursor = [], None
        for _ in range(30):
            res = self._open(urllib.request.Request(
                f"{ONEFINGER_URL}{API_PREFIX}/employees?" + urllib.parse.urlencode({"limit": 100, **({"cursor": cursor} if cursor else {})}),
                headers={"Accept": "application/json"}))
            if getattr(res, "status", getattr(res, "code", 0)) != 200:
                raise OneFingerError("직원 목록을 읽지 못했어요.", code="EMPLOYEES")
            j = json.loads(res.read().decode("utf-8", "replace") or "{}")
            out += [e for e in (j.get("data") or []) if e.get("id") and e.get("active") is not False]
            cursor = (j.get("meta") or {}).get("nextCursor")
            if not cursor:
                break
        return out

    def balance(self, month, gift_view=False):
        return self.api("GET", "/me/reward-balance", {"month": month, **({"view": "gift"} if gift_view else {})}) or {}

    def projects(self, at):
        return self.api("GET", "/me/projects", {"at": at}) or []

    def give_fruit(self, employee_id, amount, message):
        return self.api("POST", "/fruit-gifts", body={"recipients": [{"employeeId": str(employee_id), "amount": int(amount), "message": str(message or "")[:2000]}]})

    def worklog(self, date):
        try:
            return self.api("GET", f"/me/worklogs/{date}")
        except OneFingerError as exc:
            if exc.status == 404 or "NOT_FOUND" in str(exc.code or "").upper():
                return None
            raise

    def save_worklog(self, date, body):
        return self.api("PUT", f"/me/worklogs/{date}", body=body)

    def ledger(self, month, limit=100):
        out, cursor = [], None
        for _ in range(20):
            q = {"month": month, "limit": limit, **({"cursor": cursor} if cursor else {})}
            res = self._open(urllib.request.Request(f"{ONEFINGER_URL}{API_PREFIX}/me/reward-ledger?" + urllib.parse.urlencode(q), headers={"Accept": "application/json"}))
            if getattr(res, "status", getattr(res, "code", 0)) != 200:
                raise OneFingerError("열매·씨앗 내역을 읽지 못했어요.", code="LEDGER")
            j = json.loads(res.read().decode("utf-8", "replace") or "{}")
            out += j.get("data") or []
            cursor = (j.get("meta") or {}).get("nextCursor")
            if not cursor:
                break
        return out

    def rankings(self, kind, month=None, year=None):
        q = {"kind": kind}
        if kind == "level":
            q["year"] = int(year)
        else:
            q["month"] = month
        return self.api("GET", "/rankings", q) or {}

    def worklog_calendar(self, month):
        return self.api("GET", "/me/worklog-calendar", {"month": month}) or []
