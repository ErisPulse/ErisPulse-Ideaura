import asyncio
import aiohttp
import io
import json
import os
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from ErisPulse import sdk
from ErisPulse.Core import router
from ErisPulse.Core.Event import register_event_mixin, unregister_platform_event_methods


@dataclass
class IdeauraAccountConfig:
    email: str
    password: str
    enabled: bool = True
    name: str = ""
    token: str = ""
    user_id: str = ""
    username: str = ""
    avatar_url: str = ""
    inbox_topic: str = ""
    ws_session: Optional[aiohttp.ClientWebSocketResponse] = None
    heartbeat_task: Optional[asyncio.Task] = None
    receive_task: Optional[asyncio.Task] = None


class IdeauraEventMixin:
    def get_source_type(self):
        return self.get("ideaura_source_type", "")

    def get_sender_name(self):
        return self.get("ideaura_sender_name", "")

    def get_sender_avatar(self):
        return self.get("ideaura_sender_avatar", "")

    def is_sender_bot(self):
        return self.get("ideaura_sender_is_bot", False)

    def get_topic_name(self):
        return self.get("ideaura_topic_name", "")

    def get_message_type(self):
        return self.get("ideaura_message_type", "")

    def get_message_subtype(self):
        return self.get("ideaura_message_subtype", "")

    def is_self_message(self):
        return self.get("ideaura_is_self", False)


class IdeauraAdapter(sdk.BaseAdapter):

    class Send(sdk.BaseAdapter.Send):

        def __init__(self, adapter, target_type=None, target_id=None, account_id=None):
            super().__init__(adapter, target_type, target_id, account_id)
            self._at_user_ids = []
            self._reply_message_id = None

        def At(self, user_id: str, name: str = None) -> "Send":
            self._at_user_ids.append({"type": "user", "id": str(user_id)})
            return self

        def AtAll(self) -> "Send":
            self._at_user_ids.append({"type": "all"})
            return self

        def Reply(self, message_id: str) -> "Send":
            self._reply_message_id = str(message_id)
            return self

        def _reset_modifiers(self):
            self._at_user_ids = []
            self._reply_message_id = None

        def Text(self, text: str):
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file, filename: str = None):
            return self.Raw_ob12([{"type": "image", "data": {"file": file, "filename": filename}}])

        def Video(self, file, filename: str = None):
            return self.Raw_ob12([{"type": "video", "data": {"file": file, "filename": filename}}])

        def File(self, file, filename: str = None):
            return self.Raw_ob12([{"type": "file", "data": {"file": file, "filename": filename}}])

        def Face(self, face_id: str):
            return self.Raw_ob12([{"type": "text", "data": {"text": face_id}}])

        def Voice(self, file, filename: str = None):
            return self.Raw_ob12([{"type": "file", "data": {"file": file, "filename": filename}}])

        def Markdown(self, text: str):
            return self.Raw_ob12([{"type": "ideaura_markdown", "data": {"markdown": text}}])

        def Html(self, html: str):
            return self.Raw_ob12([{"type": "ideaura_html", "data": {"html": html}}])

        def Edit(self, message_id: str, text: str, content_type: str = "text"):
            return asyncio.create_task(
                self._adapter.call_api(
                    "edit_message",
                    _account_id=self._account_id,
                    messageId=str(message_id),
                    newContent=text,
                    newSubtype=content_type,
                )
            )

        def Recall(self, message_id: str):
            return asyncio.create_task(
                self._adapter.call_api(
                    "delete_message",
                    _account_id=self._account_id,
                    messageId=str(message_id),
                )
            )

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

            known = {"text", "image", "video", "file", "face", "voice", "markdown", "html"}
            lower = name.lower()
            if lower in known:
                return getattr(self, lower.capitalize())

            async def _unimplemented(*args, **kwargs):
                self._adapter.logger.debug(f"Send method '{name}' is not implemented")
                return None

            return _unimplemented

        def Raw_ob12(self, message, **kwargs):
            if isinstance(message, dict):
                message = [message]

            async def _send():
                results = []
                for segment in message:
                    result = await self._send_segment(segment)
                    if result:
                        results.append(result)
                self._reset_modifiers()
                return results[-1] if results else None

            return asyncio.create_task(_send())

        async def _send_segment(self, segment: Dict) -> Optional[Dict]:
            seg_type = segment.get("type", "")
            seg_data = segment.get("data", {})

            if seg_type == "reply":
                self._reply_message_id = seg_data.get("message_id", "")
                return None

            if seg_type in ("mention", "mention_all"):
                if seg_type == "mention_all":
                    self._at_user_ids.append({"type": "all"})
                elif seg_data.get("user_id"):
                    uid = str(seg_data["user_id"])
                    self._at_user_ids.append({"type": "user", "id": uid})
                return None

            account = self._resolve_account()
            if not account:
                raise ValueError("No available account")

            if seg_type == "text":
                return await self._send_text(seg_data.get("text", ""), account)
            elif seg_type == "image":
                return await self._send_media(seg_data, "image", account)
            elif seg_type == "video":
                return await self._send_media(seg_data, "video", account)
            elif seg_type == "file":
                return await self._send_media(seg_data, "file", account)
            elif seg_type == "ideaura_markdown":
                return await self._send_text(seg_data.get("markdown", ""), account, subtype="markdown")
            elif seg_type == "ideaura_html":
                return await self._send_text(seg_data.get("html", ""), account, subtype="html")
            else:
                text = str(seg_data)
                return await self._send_text(text, account)

        def _resolve_account(self) -> Optional[IdeauraAccountConfig]:
            adapter = self._adapter
            if self._account_id:
                if self._account_id in adapter.accounts:
                    account = adapter.accounts[self._account_id]
                    if account.enabled:
                        return account
                for name, acc in adapter.accounts.items():
                    if acc.user_id == self._account_id and acc.enabled:
                        return acc
            enabled = [a for a in adapter.accounts.values() if a.enabled]
            return enabled[0] if enabled else None

        def _build_endpoint_and_base_payload(self, account: IdeauraAccountConfig) -> tuple:
            if self._target_type == "user":
                endpoint = "/api/chat/private-messages"
                payload = {"receiverId": self._target_id}
            else:
                endpoint = "/api/chat/messages"
                payload = {}
                if self._target_id == "chatroom":
                    pass
                else:
                    payload["topicId"] = self._target_id
            if self._at_user_ids:
                payload["mentions"] = list(self._at_user_ids)
            if self._reply_message_id:
                payload["quotedMessageId"] = self._reply_message_id
            return endpoint, payload

        async def _send_text(self, text: str, account: IdeauraAccountConfig, subtype: str = "text") -> Dict:
            endpoint, payload = self._build_endpoint_and_base_payload(account)
            payload["content"] = text
            payload["messageSubtype"] = subtype
            return await self._adapter._http_post(endpoint, account, payload)

        async def _send_media(self, seg_data: Dict, media_type: str, account: IdeauraAccountConfig) -> Dict:
            file = seg_data.get("file")
            filename = seg_data.get("filename")

            file_bytes, resolved_name = await self._resolve_file(file, filename)
            if file_bytes is None:
                raise ValueError(f"Failed to resolve file: {file}")

            resolved_name = self._resolve_filename(file_bytes, resolved_name, media_type)

            endpoint, payload = self._build_endpoint_and_base_payload(account)
            payload["content"] = ""
            payload["messageSubtype"] = media_type

            return await self._adapter._http_upload_and_send(
                endpoint, account, file_bytes, resolved_name, payload
            )

        def _resolve_filename(self, file_bytes: bytes, filename: str, media_type: str) -> str:
            detected = self._detect_file_type(file_bytes)
            type_exts = {
                "image": {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "tiff"},
                "video": {"mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "3gp", "m4v"},
            }
            default_ext = {"image": "jpg", "video": "mp4", "file": "bin"}
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

            if media_type in type_exts:
                if ext in type_exts[media_type]:
                    return filename
                if detected and detected in type_exts[media_type]:
                    base = filename.rsplit(".", 1)[0] if "." in filename else filename
                    return base + "." + detected
                base = filename.rsplit(".", 1)[0] if "." in filename else filename
                return base + "." + default_ext.get(media_type, "bin")

            if detected and (not ext or ext in ("bin", "dat", "tmp")):
                base = filename.rsplit(".", 1)[0] if "." in filename else filename
                return base + "." + detected
            if ext:
                return filename

            suffix = detected or default_ext.get(media_type, "bin")
            return filename + "." + suffix

        def _detect_file_type(self, data: bytes) -> str:
            if len(data) < 12:
                return ""
            h = data[:16]
            if h[:8] == b'\x89PNG\r\n\x1a\n':
                return "png"
            if h[:2] == b'\xff\xd8':
                return "jpg"
            if h[:6] in (b'GIF87a', b'GIF89a'):
                return "gif"
            if h[:4] == b'RIFF' and h[8:12] == b'WEBP':
                return "webp"
            if h[4:8] == b'ftyp':
                return "mp4"
            if h[:3] == b'ID3' or h[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
                return "mp3"
            if h[:4] == b'RIFF' and h[8:12] == b'WAVE':
                return "wav"
            if h[:4] == b'OggS':
                return "ogg"
            if h[:5] == b'%PDF-':
                return "pdf"
            if h[:4] == b'PK\x03\x04':
                return "docx"
            if h[:4] == b'RIFF' and h[8:12] == b'AVI ':
                return "avi"
            if h[:3] == b'FLV':
                return "flv"
            return ""

        async def _resolve_file(self, file, filename: str = None) -> tuple:
            if isinstance(file, bytes):
                return file, filename or "file.bin"

            if isinstance(file, str):
                if file.startswith("http://") or file.startswith("https://"):
                    file_bytes, dl_name = await self._adapter._download_file(file)
                    if file_bytes is None:
                        return None, None
                    return file_bytes, filename or dl_name or "file.bin"

                if os.path.exists(file):
                    file_bytes, local_name = self._adapter._read_local_file(file)
                    if file_bytes is None:
                        return None, None
                    return file_bytes, filename or local_name or "file.bin"

            return None, None

    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = sdk.adapter

        self.base_url = "https://api-cofe.allons-y.uk:3009"
        self.ws_url = "wss://api-cofe.allons-y.uk:3009/mqtt"
        self.heartbeat_interval = 30
        self.reconnect_delay = 5
        self._running = False
        self.session: Optional[aiohttp.ClientSession] = None
        self.accounts: Dict[str, IdeauraAccountConfig] = self._load_accounts_config()

        super().__init__()

        self.convert = self._setup_converter()

    def _setup_converter(self):
        from .Converter import IdeauraConverter
        converter = IdeauraConverter()
        return converter.convert

    def _load_accounts_config(self) -> Dict[str, IdeauraAccountConfig]:
        accounts = {}
        account_configs = self.sdk.config.getConfig("IdeauraAdapter.accounts", {})

        if not account_configs:
            self.logger.info("No IdeauraAdapter config found, creating default")
            default_config = {
                "default": {
                    "email": "",
                    "password": "",
                    "enabled": False,
                }
            }
            try:
                self.sdk.config.setConfig("IdeauraAdapter.accounts", default_config)
            except Exception as e:
                self.logger.error(f"Failed to save default config: {e}")
            account_configs = default_config

        base_url = self.sdk.config.getConfig("IdeauraAdapter.base_url", self.base_url)
        if base_url:
            self.base_url = base_url
        ws_url = self.sdk.config.getConfig("IdeauraAdapter.ws_url", self.ws_url)
        if ws_url:
            self.ws_url = ws_url
        hb = self.sdk.config.getConfig("IdeauraAdapter.heartbeat_interval")
        if hb is not None:
            self.heartbeat_interval = int(hb)

        for name, config in account_configs.items():
            if not isinstance(config, dict):
                continue
            email = config.get("email", "")
            password = config.get("password", "")
            if not email or not password:
                self.logger.warning(f"Account '{name}' missing email/password, skipped")
                continue

            accounts[name] = IdeauraAccountConfig(
                email=email,
                password=password,
                enabled=config.get("enabled", True),
                name=name,
            )

        self.logger.info(f"IdeauraAdapter initialized with {len(accounts)} account(s)")
        return accounts

    async def start(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=300, connect=30)
            self.session = aiohttp.ClientSession(timeout=timeout)

        register_event_mixin("ideaura", IdeauraEventMixin)

        self._running = True
        enabled_accounts = {n: a for n, a in self.accounts.items() if a.enabled}

        if not enabled_accounts:
            self.logger.warning("No enabled accounts, adapter started but idle")
            return

        for name, account in enabled_accounts.items():
            asyncio.create_task(self._start_account(name, account))

        self.logger.info(f"IdeauraAdapter started with {len(enabled_accounts)} account(s)")

    async def _start_account(self, name: str, account: IdeauraAccountConfig):
        try:
            await self._login(account)
            await self._get_user_info(account)
            await self._get_inbox_topic(account)

            await self.adapter.emit({
                "type": "meta",
                "detail_type": "connect",
                "platform": "ideaura",
                "self": {
                    "platform": "ideaura",
                    "user_id": account.user_id,
                    "user_name": account.username,
                    "nickname": account.username,
                    "avatar": account.avatar_url,
                    "account_id": name,
                },
            })

            await self._connect_websocket(name, account)
        except Exception as e:
            self.logger.error(f"Account '{name}' start failed: {e}")

    async def _login(self, account: IdeauraAccountConfig):
        url = f"{self.base_url}/api/auth/login"
        payload = {
            "email": account.email,
            "password": account.password,
        }

        async with self.session.post(url, json=payload) as resp:
            data = await resp.json()

        token = data.get("token") or data.get("data", {}).get("token")
        if not token:
            raise ValueError(f"Login failed for {account.email}: {data}")

        account.token = token

        user_data = data.get("data", {}).get("user", data.get("data", {}))
        if not user_data:
            user_data = data
        account.user_id = str(user_data.get("id", data.get("userId", "")))

        self.logger.info(f"Account {account.name} logged in (user_id={account.user_id})")

    async def _get_user_info(self, account: IdeauraAccountConfig):
        if account.username:
            return
        url = f"{self.base_url}/api/users/me"
        headers = {"Authorization": f"Bearer {account.token}"}

        try:
            async with self.session.get(url, headers=headers) as resp:
                data = await resp.json()
            if data.get("success"):
                user_data = data.get("data", {})
                account.username = user_data.get("username", "")
                account.avatar_url = user_data.get("avatarUrl", "")
        except Exception as e:
            self.logger.debug(f"Failed to get user info for {account.name}: {e}")

    async def _get_inbox_topic(self, account: IdeauraAccountConfig):
        url = f"{self.base_url}/api/chat/user-inbox-topic"
        headers = {"Authorization": f"Bearer {account.token}"}

        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()

        resp_data = data.get("data", {})
        topic = resp_data.get("inboxTopic") or resp_data.get("topic") or data.get("topic")
        if not topic:
            raise ValueError(f"Failed to get inbox topic for {account.name}: {data}")

        account.inbox_topic = topic

        if resp_data.get("userId") and not account.user_id:
            account.user_id = str(resp_data["userId"])

        self.logger.debug(f"Account {account.name} inbox topic: {topic}")

    async def _connect_websocket(self, name: str, account: IdeauraAccountConfig):
        while self._running:
            try:
                async with self.session.ws_connect(self.ws_url) as ws:
                    account.ws_session = ws

                    await ws.send_json({"type": "connect", "token": account.token})

                    msg = await ws.receive(timeout=30)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        raise ValueError(f"Unexpected WS message type: {msg.type}")

                    connack = json.loads(msg.data)
                    if connack.get("type") != "connack":
                        raise ValueError(f"Expected connack, got: {connack}")

                    await ws.send_json({
                        "type": "subscribe",
                        "topics": [account.inbox_topic],
                    })

                    sub_msg = await ws.receive(timeout=30)
                    if sub_msg.type == aiohttp.WSMsgType.TEXT:
                        suback = json.loads(sub_msg.data)
                        self.logger.debug(f"Account {name} subscribe response: {suback}")

                    account.heartbeat_task = asyncio.create_task(
                        self._heartbeat_loop(name, account, ws)
                    )
                    account.receive_task = asyncio.create_task(
                        self._receive_loop(name, account, ws)
                    )

                    await account.receive_task

                    if account.heartbeat_task and not account.heartbeat_task.done():
                        account.heartbeat_task.cancel()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Account {name} WS error: {e}")

            account.ws_session = None
            if self._running:
                self.logger.info(f"Account {name} reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

    async def _heartbeat_loop(self, name: str, account: IdeauraAccountConfig, ws):
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await ws.send_json({"type": "pingreq"})

                await self.adapter.emit({
                    "type": "meta",
                    "detail_type": "heartbeat",
                    "platform": "ideaura",
                    "self": {
                        "platform": "ideaura",
                        "user_id": account.user_id,
                        "account_id": name,
                    },
                })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.debug(f"Account {name} heartbeat stopped: {e}")

    async def _receive_loop(self, name: str, account: IdeauraAccountConfig, ws):
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message(name, account, data)
                    except json.JSONDecodeError:
                        self.logger.warning(f"Account {name} invalid JSON from WS")
                    except Exception as e:
                        self.logger.error(f"Account {name} message handling error: {e}")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Account {name} receive loop error: {e}")

    async def _handle_ws_message(self, name: str, account: IdeauraAccountConfig, data: Dict):
        msg_type = data.get("type", "")

        if msg_type == "pingresp":
            return

        self.logger.debug(f"Account {name} WS message: {json.dumps(data, ensure_ascii=False)[:500]}")

        if msg_type == "publish":
            payload_raw = data.get("payload", {})
            if isinstance(payload_raw, str):
                try:
                    payload_raw = json.loads(payload_raw)
                except json.JSONDecodeError:
                    self.logger.warning(f"Account {name} invalid publish payload")
                    return

            event = self.convert(payload_raw, account.user_id)
            if event:
                self.logger.debug(f"Account {name} event: {json.dumps(event, ensure_ascii=False)[:500]}")
                await self.adapter.emit(event)
        elif msg_type in ("connack", "suback"):
            pass
        else:
            self.logger.debug(f"Account {name} unhandled WS message type: {msg_type}")

    async def shutdown(self):
        self._running = False

        for name, account in self.accounts.items():
            if account.enabled:
                try:
                    await self.adapter.emit({
                        "type": "meta",
                        "detail_type": "disconnect",
                        "platform": "ideaura",
                        "self": {
                            "platform": "ideaura",
                            "user_id": account.user_id,
                            "account_id": name,
                        },
                    })
                except Exception:
                    pass

                if account.heartbeat_task and not account.heartbeat_task.done():
                    account.heartbeat_task.cancel()
                if account.receive_task and not account.receive_task.done():
                    account.receive_task.cancel()
                if account.ws_session and not account.ws_session.closed:
                    await account.ws_session.close()

        unregister_platform_event_methods("ideaura")

        if self.session:
            await self.session.close()
            self.session = None

        self.logger.info("IdeauraAdapter shutdown complete")

    async def call_api(self, endpoint: str, _account_id: str = None, **params):
        account = self._resolve_account_for_api(_account_id)

        if endpoint == "edit_message":
            return await self._api_edit_message(account, **params)
        elif endpoint == "delete_message":
            return await self._api_delete_message(account, **params)

        api_path = endpoint if endpoint.startswith("/api/") else f"/api/{endpoint}"
        return await self._http_request("POST", api_path, account, params)

    def _resolve_account_for_api(self, _account_id: str = None) -> IdeauraAccountConfig:
        if _account_id:
            if _account_id in self.accounts:
                account = self.accounts[_account_id]
                if account.enabled:
                    return account
            for name, acc in self.accounts.items():
                if acc.user_id == _account_id and acc.enabled:
                    return acc

        enabled = [a for a in self.accounts.values() if a.enabled]
        if not enabled:
            raise ValueError("No enabled accounts")
        return enabled[0]

    async def _api_edit_message(self, account: IdeauraAccountConfig, **params) -> Dict:
        message_id = str(params.get("messageId", ""))
        new_content = params.get("newContent", "")
        new_subtype = params.get("newSubtype", "text")

        return await self._http_request(
            "PUT",
            f"/api/chat/messages/{message_id}",
            account,
            {"content": new_content, "isPrivate": "false"},
        )

    async def _api_delete_message(self, account: IdeauraAccountConfig, **params) -> Dict:
        message_id = str(params.get("messageId", ""))
        query_parts = []
        is_private = params.get("isPrivate")
        topic_id = params.get("topicId")
        if is_private is not None:
            query_parts.append(f"isPrivate={str(is_private).lower()}")
        if topic_id is not None:
            query_parts.append(f"topicId={topic_id}")
        qs = ("?" + "&".join(query_parts)) if query_parts else ""

        return await self._http_request(
            "DELETE",
            f"/api/chat/messages/{message_id}{qs}",
            account,
            None,
        )

    def _ensure_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=300, connect=30)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def _http_post(self, endpoint: str, account: IdeauraAccountConfig, data: Dict) -> Dict:
        self._ensure_session()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {account.token}",
            "Content-Type": "application/json",
        }

        self.logger.debug(f"Account {account.name} POST {endpoint}: {json.dumps(data, ensure_ascii=False)[:500]}")

        try:
            async with self.session.post(url, json=data, headers=headers) as resp:
                raw = await self._parse_response(resp)
                return self._standardize_response(raw, account)

        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP POST failed {endpoint}: {e}")
            return self._error_response(str(e), 33000)

    async def _http_upload_and_send(
        self, endpoint: str, account: IdeauraAccountConfig,
        file_bytes: bytes, filename: str, payload: Dict
    ) -> Dict:
        self._ensure_session()

        url = f"{self.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {account.token}"}

        content_type = self._guess_content_type(filename)
        form = aiohttp.FormData()
        form.add_field("file", io.BytesIO(file_bytes), filename=filename, content_type=content_type)

        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                form.add_field(key, json.dumps(value))
            else:
                form.add_field(key, str(value))

        self.logger.debug(f"Account {account.name} POST (multipart+file) {endpoint} file={filename}")

        try:
            async with self.session.post(url, data=form, headers=headers) as resp:
                raw = await self._parse_response(resp)
                return self._standardize_response(raw, account)
        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP upload+send failed {endpoint}: {e}")
            return self._error_response(str(e), 33000)

    async def _http_request(self, method: str, endpoint: str, account: IdeauraAccountConfig, params: Dict = None) -> Dict:
        self._ensure_session()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {account.token}",
            "Content-Type": "application/json",
        }

        try:
            async with self.session.request(method, url, json=params, headers=headers) as resp:
                raw = await self._parse_response(resp)
                return self._standardize_response(raw, account)

        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP {method} failed {endpoint}: {e}")
            return self._error_response(str(e), 33000)

    async def _parse_response(self, resp) -> Dict:
        if resp.content_type and "json" in resp.content_type:
            return await resp.json()

        text = await resp.text()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def _standardize_response(self, raw: Dict, account: IdeauraAccountConfig) -> Dict:
        success = raw.get("success", raw.get("ok", False))
        if isinstance(success, str):
            success = success.lower() == "true"

        status_code = raw.get("statusCode", raw.get("code", 0))

        result = {
            "status": "ok" if success or (200 <= status_code < 300 if isinstance(status_code, int) else False) else "failed",
            "retcode": 0 if success else (status_code or -1),
            "data": raw.get("data", raw),
            "message": raw.get("message", raw.get("msg", "")),
            "ideaura_raw": raw,
            "self": {"user_id": account.user_id},
        }

        message_id = ""
        data = raw.get("data", {})
        if isinstance(data, dict):
            message_id = data.get("messageId", data.get("id", ""))
        result["message_id"] = str(message_id)
        if isinstance(result["data"], dict):
            result["data"]["message_id"] = result["message_id"]

        return result

    def _error_response(self, message: str, retcode: int = 34000) -> Dict:
        return {
            "status": "failed",
            "retcode": retcode,
            "data": None,
            "message_id": "",
            "message": message,
            "ideaura_raw": None,
        }

    async def _upload_file(self, account: IdeauraAccountConfig, file_bytes: bytes, filename: str) -> Optional[Dict]:
        self._ensure_session()

        url = f"{self.base_url}/api/chat/upload"
        headers = {"Authorization": f"Bearer {account.token}"}

        content_type = self._guess_content_type(filename)
        data = aiohttp.FormData()
        data.add_field("file", io.BytesIO(file_bytes), filename=filename, content_type=content_type)

        try:
            timeout = aiohttp.ClientTimeout(total=600, connect=30)
            async with self.session.post(url, data=data, headers=headers, timeout=timeout) as resp:
                if resp.status == 413:
                    self.logger.error("File too large for upload")
                    return None

                if resp.status >= 500:
                    text = await resp.text()
                    self.logger.error(f"File upload server error {resp.status}: {text[:200]}")
                    return None

                try:
                    raw = await resp.json()
                except Exception:
                    text = await resp.text()
                    self.logger.error(f"File upload bad response (status={resp.status}): {text[:200]}")
                    return None

                if not raw.get("success", False):
                    self.logger.error(f"File upload failed: {raw.get('message', raw)}")
                    return None

                self.logger.debug(f"Upload response: {raw}")
                return raw

        except aiohttp.ClientError as e:
            self.logger.error(f"File upload failed: {e}")
            return None

    async def _download_file(self, url: str, max_size: int = 10 * 1024 * 1024) -> tuple:
        self._ensure_session()

        try:
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            filename = unquote(parsed.path.split("/")[-1]) or "downloaded_file"

            async with self.session.get(url) as resp:
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > max_size:
                    self.logger.warning(f"File too large: {int(content_length) / 1024 / 1024:.2f}MB")
                    return None, None

                buffer = io.BytesIO()
                downloaded = 0
                async for chunk in resp.content.iter_chunked(8192):
                    downloaded += len(chunk)
                    if downloaded > max_size:
                        self.logger.warning("File too large during download")
                        return None, None
                    buffer.write(chunk)

                buffer.seek(0)
                return buffer.read(), filename

        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return None, None

    def _read_local_file(self, file_path: str, max_size: int = 10 * 1024 * 1024) -> tuple:
        try:
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                self.logger.error(f"File not found: {file_path}")
                return None, None

            size = os.path.getsize(file_path)
            if size > max_size:
                self.logger.warning(f"File too large: {size / 1024 / 1024:.2f}MB")
                return None, None

            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                return f.read(), filename

        except Exception as e:
            self.logger.error(f"Read file failed: {e}")
            return None, None

    def _guess_content_type(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        type_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
            "mp4": "video/mp4", "avi": "video/x-msvideo", "mov": "video/quicktime",
            "mkv": "video/x-matroska", "webm": "video/webm",
            "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "flac": "audio/flac",
            "pdf": "application/pdf", "zip": "application/zip",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain", "json": "application/json",
        }
        return type_map.get(ext, "application/octet-stream")
