import asyncio
import io
import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from ErisPulse.Core import client, router
from ErisPulse.Core.Bases.adapter import BaseAdapter
from ErisPulse.Core.Bases.websocket import WSMessage
from ErisPulse.runtime.config_schema import (
    BotAccountConfig,
    AdapterConfig,
    dict_to_dataclass,
)
from ErisPulse.Core.config import config as config_mgr
from ErisPulse.Core.Event import register_event_mixin, unregister_platform_event_methods


@dataclass
class IdeauraConfig(AdapterConfig):
    base_url: str = field(
        default="https://api.mscpo.com/api/rockychat",
        metadata={
            "description": "花枫咖啡馆 API 基础地址",
            "required": False,
            "webui": {"widget": "text", "group": "connection", "order": 1},
        },
    )
    ws_url: str = field(
        default="wss://api-cofe.allons-y.uk:3009/mqtt",
        metadata={
            "description": "花枫咖啡馆 WebSocket 地址",
            "required": False,
            "webui": {"widget": "text", "group": "connection", "order": 2},
        },
    )
    heartbeat_interval: int = field(
        default=30,
        metadata={
            "description": "心跳间隔（秒）",
            "required": False,
            "webui": {"widget": "number", "group": "advanced", "order": 3},
        },
    )
    reconnect_delay: int = field(
        default=5,
        metadata={
            "description": "重连延迟（秒）",
            "required": False,
            "webui": {"widget": "number", "group": "advanced", "order": 4},
        },
    )


@dataclass
class IdeauraAccountConfig(BotAccountConfig):
    token: str = field(
        default="",
        metadata={
            "description": "Bot Token（机器人 API Token）",
            "required": True,
            "secret": True,
            "webui": {"widget": "password", "group": "token", "order": 1},
        },
    )

    def has_valid_auth(self) -> bool:
        """账户是否提供了有效的 Bot Token"""
        return bool(self.token)


class IdeauraEventMixin:
    def get_source_type(self):
        return self.get("ideaura_source_type", "")

    def get_sender_name(self):
        return self.get("ideaura_sender_name", "")

    def get_sender_avatar(self):
        return self.get("ideaura_sender_avatar", "")

    def is_sender_bot(self):
        return self.get("ideaura_sender_is_bot", False)

    def is_receiver_bot(self):
        return self.get("ideaura_receiver_is_bot", False)

    def get_command_id(self):
        return self.get("ideaura_command_id", "")

    def get_command(self):
        return self.get("ideaura_command_id", "")

    def get_topic_name(self):
        return self.get("ideaura_topic_name", "")

    def get_message_type(self):
        return self.get("ideaura_message_type", "")

    def get_message_subtype(self):
        return self.get("ideaura_message_subtype", "")

    def is_self_message(self):
        return self.get("ideaura_is_self", False)


class IdeauraAdapter(BaseAdapter):

    AccountConfigClass = IdeauraAccountConfig
    ConfigClass = IdeauraConfig

    class Send(BaseAdapter.Send):

        def __init__(self, adapter, target_type=None, target_id=None, account_id=None):
            super().__init__(adapter, target_type, target_id, account_id)
            self._command_id = None

        def Command(self, command_id: str):
            self._command_id = command_id
            return self

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
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    "edit_message",
                    _account_id=ctx.get("account_id"),
                    messageId=str(message_id),
                    newContent=text,
                    newSubtype=content_type,
                )
            )

        def Recall(self, message_id: str):
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    "delete_message",
                    _account_id=ctx.get("account_id"),
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
                return results[-1] if results else None

            return asyncio.create_task(_send())

        async def _send_segment(self, segment: Dict) -> Optional[Dict]:
            seg_type = segment.get("type", "")
            seg_data = segment.get("data", {})

            if seg_type == "reply":
                self._reply_message_id = seg_data.get("message_id", "")
                return None

            if seg_type == "ideaura_command":
                cmd_id = seg_data.get("command_id") or seg_data.get("commandId", "")
                if cmd_id:
                    self._command_id = str(cmd_id)
                return None

            if seg_type in ("mention", "mention_all"):
                if seg_type == "mention_all":
                    self._at_user_ids.append({"type": "all"})
                elif seg_data.get("user_id"):
                    uid = str(seg_data["user_id"])
                    self._at_user_ids.append({"type": "user", "id": uid})
                return None

            ctx = self.send_context
            account_name, account = self._adapter._resolve_account(ctx.get("account_id"))
            if not account:
                raise ValueError("No available account")

            if seg_type == "text":
                return await self._send_text(seg_data.get("text", ""), account_name, account)
            elif seg_type == "image":
                return await self._send_media(seg_data, "image", account_name, account)
            elif seg_type == "video":
                return await self._send_media(seg_data, "video", account_name, account)
            elif seg_type == "file":
                return await self._send_media(seg_data, "file", account_name, account)
            elif seg_type == "ideaura_markdown":
                return await self._send_text(seg_data.get("markdown", ""), account_name, account, subtype="markdown")
            elif seg_type == "ideaura_html":
                return await self._send_text(seg_data.get("html", ""), account_name, account, subtype="html")
            else:
                text = str(seg_data)
                return await self._send_text(text, account_name, account)

        def _build_endpoint_and_base_payload(self, account_name: str) -> tuple:
            ctx = self.send_context
            target_type = ctx.get("target_type")
            target_id = ctx.get("target_id")
            if target_type == "user":
                endpoint = "/api/chat/private-messages"
                payload = {"receiverId": target_id}
            else:
                endpoint = "/api/chat/messages"
                payload = {}
                if target_id == "chatroom":
                    pass
                else:
                    payload["topicId"] = target_id
            if self._at_user_ids:
                payload["mentions"] = list(self._at_user_ids)
            if self._reply_message_id:
                payload["quotedMessageId"] = self._reply_message_id
            if self._command_id:
                payload["commandId"] = self._command_id
            return endpoint, payload

        async def _send_text(self, text: str, account_name: str, account: IdeauraAccountConfig, subtype: str = "text") -> Dict:
            endpoint, payload = self._build_endpoint_and_base_payload(account_name)
            payload["content"] = text
            payload["messageSubtype"] = subtype
            return await self._adapter._http_post(endpoint, account_name, account, payload)

        async def _send_media(self, seg_data: Dict, media_type: str, account_name: str, account: IdeauraAccountConfig) -> Dict:
            file = seg_data.get("file")
            filename = seg_data.get("filename")

            file_bytes, resolved_name = await self._resolve_file(file, filename)
            if file_bytes is None:
                raise ValueError(f"Failed to resolve file: {file}")

            resolved_name = self._resolve_filename(file_bytes, resolved_name, media_type)

            endpoint, payload = self._build_endpoint_and_base_payload(account_name)
            payload["content"] = ""
            payload["messageSubtype"] = media_type

            return await self._adapter._http_upload_and_send(
                endpoint, account_name, account, file_bytes, resolved_name, payload
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

    def __init__(self, sdk_ref=None):
        super().__init__(sdk_ref)
        self._running = False
        # 每个账户的运行时状态（登录后获得，不属于配置）
        # _runtime_state[name] = {token, user_id, username, avatar_url, inbox_topic,
        #                         ws_session, heartbeat_task, receive_task}
        self._runtime_state: Dict[str, dict] = {}
        self.convert = self._setup_converter()

    def _get_config_key(self) -> str:
        return "IdeauraAdapter"

    def _load_accounts(self) -> dict:
        key = "IdeauraAdapter.accounts"
        data = config_mgr.getConfig(key)

        if not data:
            self.logger.info("未找到 IdeauraAdapter 账户配置，创建默认配置")
            data = {
                "default": {
                    "token": "",
                    "enabled": True,
                }
            }
            try:
                config_mgr.setConfig(key, data)
            except Exception as e:
                self.logger.error(f"保存默认配置失败: {e}")

        accounts = {}
        for name, account_data in data.items():
            if not isinstance(account_data, dict):
                continue

            instance = dict_to_dataclass(IdeauraAccountConfig, account_data)
            instance.name = name

            if not instance.has_valid_auth():
                self.logger.warning(
                    f"账户 '{name}' 缺少有效认证信息（需提供 token），已跳过"
                )
                continue

            accounts[name] = instance

        self.logger.info(f"IdeauraAdapter 初始化完成，共加载 {len(accounts)} 个账户")
        return accounts

    def _get_global_config(self) -> IdeauraConfig:
        data = config_mgr.getConfig("IdeauraAdapter") or {}
        return dict_to_dataclass(IdeauraConfig, data)

    def _setup_converter(self):
        from .Converter import IdeauraConverter
        converter = IdeauraConverter()
        return converter.convert

    def _get_state(self, name: str) -> dict:
        if name not in self._runtime_state:
            self._runtime_state[name] = {}
        return self._runtime_state[name]

    async def start(self):
        register_event_mixin("ideaura", IdeauraEventMixin)

        self._running = True
        if not self.enabled_accounts:
            self.logger.warning("没有已启用的账户，适配器将以空闲状态启动")
            return

        for name, account in self.enabled_accounts.items():
            asyncio.create_task(self._start_account(name, account))

        self.logger.info(f"IdeauraAdapter 已启动，共 {len(self.enabled_accounts)} 个账户")

    async def _start_account(self, name: str, account: IdeauraAccountConfig):
        try:
            await self._login(name, account)
            await self._get_user_info(name, account)
            await self._get_inbox_topic(name, account)

            state = self._get_state(name)
            await self.emit_meta("connect", state.get("user_id", ""))

            await self._connect_websocket(name, account)
        except Exception as e:
            self.logger.error(f"账户 '{name}' 启动失败: {e}")

    async def _login(self, name: str, account: IdeauraAccountConfig):
        state = self._get_state(name)
        if not account.token:
            raise ValueError(f"账户 {name} 缺少 Bot Token")
        state["token"] = account.token
        self.logger.info(f"账户 {name} 已加载 Bot Token")

    async def _get_user_info(self, name: str, account: IdeauraAccountConfig):
        state = self._get_state(name)
        if state.get("username"):
            return

        cfg = self._get_global_config()
        url = f"{cfg.base_url}/api/users/me"
        headers = {"Authorization": f"Bearer {state.get('token', '')}"}

        try:
            resp = await client.get(url, headers=headers)
            data = await resp.json()
            if data.get("success"):
                user_data = data.get("data", {})
                state["username"] = user_data.get("username", "")
                state["avatar_url"] = user_data.get("avatarUrl", "")
        except Exception as e:
            self.logger.debug(f"获取账户 {name} 用户信息失败: {e}")

    async def _get_inbox_topic(self, name: str, account: IdeauraAccountConfig):
        state = self._get_state(name)
        cfg = self._get_global_config()
        url = f"{cfg.base_url}/api/chat/user-inbox-topic"
        headers = {"Authorization": f"Bearer {state.get('token', '')}"}

        resp = await client.get(url, headers=headers)
        data = await resp.json()

        resp_data = data.get("data", {})
        topic = resp_data.get("inboxTopic") or resp_data.get("topic") or data.get("topic")
        internal_token = resp_data.get("internalToken")
        if not topic:
            raise ValueError(f"Failed to get inbox topic for {name}: {data}")
        if not internal_token:
            raise ValueError(f"Failed to get internalToken for {name}: {data}")

        state["inbox_topic"] = topic
        state["internal_token"] = internal_token

        if resp_data.get("userId") and not state.get("user_id"):
            state["user_id"] = str(resp_data["userId"])

        self.logger.debug(f"账户 {name} inbox topic: {topic}")

    async def _connect_websocket(self, name: str, account: IdeauraAccountConfig):
        cfg = self._get_global_config()
        state = self._get_state(name)

        while self._running:
            try:
                await self._get_inbox_topic(name, account)
                internal_token = state.get("internal_token", "")

                ws = await client.ws_connect(cfg.ws_url)
                state["ws_session"] = ws

                await ws.send_json({"type": "connect", "token": internal_token})

                msg = await asyncio.wait_for(ws.receive(), timeout=30)
                if msg.type != WSMessage.TEXT:
                    raise ValueError(f"Unexpected WS message type: {msg.type}")

                connack = json.loads(msg.data)
                if connack.get("type") != "connack" or connack.get("returnCode", 0) != 0:
                    raise ValueError(f"WS authentication failed, connack: {connack}")

                await ws.send_json({
                    "type": "subscribe",
                    "topics": [state.get("inbox_topic")],
                })

                sub_msg = await asyncio.wait_for(ws.receive(), timeout=30)
                if sub_msg.type == WSMessage.TEXT:
                    suback = json.loads(sub_msg.data)
                    self.logger.debug(f"账户 {name} subscribe 响应: {suback}")

                state["heartbeat_task"] = asyncio.create_task(
                    self._heartbeat_loop(name, ws)
                )
                state["receive_task"] = asyncio.create_task(
                    self._receive_loop(name, ws)
                )

                await state["receive_task"]

                if state.get("heartbeat_task") and not state["heartbeat_task"].done():
                    state["heartbeat_task"].cancel()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"账户 {name} WS 错误: {e}")

            state["ws_session"] = None
            if self._running:
                self.logger.info(f"账户 {name} 将在 {cfg.reconnect_delay}s 后重连...")
                await asyncio.sleep(cfg.reconnect_delay)

    async def _heartbeat_loop(self, name: str, ws):
        cfg = self._get_global_config()
        state = self._get_state(name)
        try:
            while True:
                await asyncio.sleep(cfg.heartbeat_interval)
                await ws.send_json({"type": "pingreq"})

                await self.emit_meta("heartbeat", state.get("user_id", ""))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.debug(f"账户 {name} 心跳停止: {e}")

    async def _receive_loop(self, name: str, ws):
        state = self._get_state(name)
        try:
            while True:
                msg = await ws.receive()
                if msg.type == WSMessage.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message(name, data)
                    except json.JSONDecodeError:
                        self.logger.warning(f"账户 {name} 收到无效的 JSON 数据")
                    except Exception as e:
                        self.logger.error(f"账户 {name} 消息处理错误: {e}")
                elif msg.type in (WSMessage.CLOSE, WSMessage.ERROR):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"账户 {name} 接收循环错误: {e}")

    async def _handle_ws_message(self, name: str, data: Dict):
        state = self._get_state(name)
        msg_type = data.get("type", "")

        if msg_type == "pingresp":
            return

        self.logger.debug(f"账户 {name} WS 消息: {json.dumps(data, ensure_ascii=False)[:500]}")

        if msg_type == "publish":
            payload_raw = data.get("payload", {})
            if isinstance(payload_raw, str):
                try:
                    payload_raw = json.loads(payload_raw)
                except json.JSONDecodeError:
                    self.logger.warning(f"账户 {name} 无效的 publish payload")
                    return

            event = self.convert(payload_raw, state.get("user_id", ""))
            if event:
                self.logger.debug(f"账户 {name} 事件: {json.dumps(event, ensure_ascii=False)[:500]}")
                from ErisPulse.Core import adapter as adapter_mgr
                await adapter_mgr.emit(event)
        elif msg_type in ("connack", "suback"):
            pass
        else:
            self.logger.debug(f"账户 {name} 未处理的 WS 消息类型: {msg_type}")

    async def shutdown(self):
        self._running = False

        for name in list(self._runtime_state.keys()):
            state = self._runtime_state[name]
            try:
                await self.emit_meta("disconnect", state.get("user_id", ""))
            except Exception:
                pass

            if state.get("heartbeat_task") and not state["heartbeat_task"].done():
                state["heartbeat_task"].cancel()
            if state.get("receive_task") and not state["receive_task"].done():
                state["receive_task"].cancel()
            if state.get("ws_session") and not state["ws_session"].closed:
                try:
                    await state["ws_session"].close()
                except Exception:
                    pass

        try:
            unregister_platform_event_methods("ideaura")
        except Exception:
            pass

        self.logger.info("IdeauraAdapter 已关闭")

    async def call_api(self, endpoint: str, _account_id: str = None, method: str = None, **params):
        account_name, account = self._resolve_account(_account_id)
        echo = params.pop("echo", None)

        try:
            if endpoint == "edit_message":
                result = await self._api_edit_message(account_name, account, **params)
            elif endpoint == "delete_message":
                result = await self._api_delete_message(account_name, account, **params)
            else:
                api_path = endpoint if endpoint.startswith("/api/") else f"/api/{endpoint}"
                http_method = method.upper() if method else ("GET" if not params else "POST")
                result = await self._http_request(http_method, api_path, account_name, account, params)

            if echo is not None:
                result["echo"] = echo
            return result
        except Exception as e:
            err = self.make_error(retcode=33001, message=str(e), raw=None)
            if echo is not None:
                err["echo"] = echo
            return err

    async def _api_edit_message(self, account_name: str, account: IdeauraAccountConfig, **params) -> Dict:
        message_id = str(params.get("messageId", ""))
        new_content = params.get("newContent", "")

        return await self._http_request(
            "PUT",
            f"/api/chat/messages/{message_id}",
            account_name,
            account,
            {"content": new_content, "isPrivate": "false"},
        )

    async def _api_delete_message(self, account_name: str, account: IdeauraAccountConfig, **params) -> Dict:
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
            account_name,
            account,
            None,
        )

    async def _http_post(self, endpoint: str, account_name: str, account: IdeauraAccountConfig, data: Dict) -> Dict:
        cfg = self._get_global_config()
        state = self._get_state(account_name)
        url = f"{cfg.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {state.get('token', '')}",
            "Content-Type": "application/json",
        }

        self.logger.debug(f"账户 {account_name} POST {endpoint}: {json.dumps(data, ensure_ascii=False)[:500]}")

        try:
            resp = await client.post(url, json=data, headers=headers)
            raw = await self._parse_response(resp)
            return self._standardize_response(raw, account_name)
        except Exception as e:
            self.logger.error(f"HTTP POST 失败 {endpoint}: {e}")
            return self.make_error(retcode=33000, message=str(e), raw=None)

    async def _http_upload_and_send(
        self, endpoint: str, account_name: str, account: IdeauraAccountConfig,
        file_bytes: bytes, filename: str, payload: Dict
    ) -> Dict:
        import aiohttp

        cfg = self._get_global_config()
        state = self._get_state(account_name)
        url = f"{cfg.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {state.get('token', '')}"}

        content_type = self._guess_content_type(filename)
        form = aiohttp.FormData()
        form.add_field("file", io.BytesIO(file_bytes), filename=filename, content_type=content_type)

        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                form.add_field(key, json.dumps(value))
            else:
                form.add_field(key, str(value))

        self.logger.debug(f"账户 {account_name} POST (multipart+file) {endpoint} file={filename}")

        try:
            resp = await client.post(url, data=form, headers=headers, timeout=300)
            raw = await self._parse_response(resp)
            return self._standardize_response(raw, account_name)
        except Exception as e:
            self.logger.error(f"HTTP upload+send 失败 {endpoint}: {e}")
            return self.make_error(retcode=33000, message=str(e), raw=None)

    async def _http_request(self, method: str, endpoint: str, account_name: str, account: IdeauraAccountConfig, params: Dict = None) -> Dict:
        cfg = self._get_global_config()
        state = self._get_state(account_name)
        url = f"{cfg.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {state.get('token', '')}",
            "Content-Type": "application/json",
        }

        try:
            resp = await client.request(method, url, json=params, headers=headers)
            raw = await self._parse_response(resp)
            return self._standardize_response(raw, account_name)
        except Exception as e:
            self.logger.error(f"HTTP {method} 失败 {endpoint}: {e}")
            return self.make_error(retcode=33000, message=str(e), raw=None)

    async def _parse_response(self, resp) -> Dict:
        try:
            return await resp.json()
        except Exception:
            text = await resp.text()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}

    def _standardize_response(self, raw: Dict, account_name: str) -> Dict:
        state = self._get_state(account_name)
        if not isinstance(raw, dict):
            return self.make_error(
                retcode=34000,
                message=f"API 返回了意外格式: {type(raw)}",
                raw=raw,
            )

        success = raw.get("success", raw.get("ok", False))
        if isinstance(success, str):
            success = success.lower() == "true"

        status_code = raw.get("statusCode", raw.get("code", 0))
        http_ok = 200 <= status_code < 300 if isinstance(status_code, int) else False
        is_ok = bool(success) or http_ok

        data = raw.get("data", raw)
        message_id = ""
        if isinstance(data, dict):
            message_id = str(data.get("messageId", data.get("id", "")))

        response = self.make_response(
            status="ok" if is_ok else "failed",
            retcode=0 if is_ok else (status_code if isinstance(status_code, int) and status_code else -1),
            data=data,
            message_id=message_id,
            message="" if is_ok else raw.get("message", raw.get("msg", "")),
            raw=raw,
        )
        response["ideaura_raw"] = raw
        response["self"] = {"user_id": state.get("user_id", "")}
        return response

    async def _upload_file(self, account_name: str, account: IdeauraAccountConfig, file_bytes: bytes, filename: str) -> Optional[Dict]:
        import aiohttp

        cfg = self._get_global_config()
        state = self._get_state(account_name)
        url = f"{cfg.base_url}/api/chat/upload"
        headers = {"Authorization": f"Bearer {state.get('token', '')}"}

        content_type = self._guess_content_type(filename)
        data = aiohttp.FormData()
        data.add_field("file", io.BytesIO(file_bytes), filename=filename, content_type=content_type)

        try:
            resp = await client.post(url, data=data, headers=headers, timeout=600)
            if resp.status == 413:
                self.logger.error("文件过大，无法上传")
                return None

            if resp.status >= 500:
                text = await resp.text()
                self.logger.error(f"文件上传服务器错误 {resp.status}: {text[:200]}")
                return None

            try:
                raw = await resp.json()
            except Exception:
                text = await resp.text()
                self.logger.error(f"文件上传响应异常 (status={resp.status}): {text[:200]}")
                return None

            if not raw.get("success", False):
                self.logger.error(f"文件上传失败: {raw.get('message', raw)}")
                return None

            self.logger.debug(f"上传响应: {raw}")
            return raw
        except Exception as e:
            self.logger.error(f"文件上传失败: {e}")
            return None

    async def _download_file(self, url: str, max_size: int = 10 * 1024 * 1024) -> tuple:
        try:
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            filename = unquote(parsed.path.split("/")[-1]) or "downloaded_file"

            resp = await client.get(url, timeout=300)
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_size:
                self.logger.warning(f"文件过大: {int(content_length) / 1024 / 1024:.2f}MB")
                return None, None

            buffer = io.BytesIO()
            downloaded = 0
            async for chunk in resp.raw.content.iter_chunked(8192):
                downloaded += len(chunk)
                if downloaded > max_size:
                    self.logger.warning("下载过程中文件过大")
                    return None, None
                buffer.write(chunk)

            buffer.seek(0)
            return buffer.read(), filename
        except Exception as e:
            self.logger.error(f"下载失败: {e}")
            return None, None

    def _read_local_file(self, file_path: str, max_size: int = 10 * 1024 * 1024) -> tuple:
        try:
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                self.logger.error(f"文件不存在: {file_path}")
                return None, None

            size = os.path.getsize(file_path)
            if size > max_size:
                self.logger.warning(f"文件过大: {size / 1024 / 1024:.2f}MB")
                return None, None

            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                return f.read(), filename
        except Exception as e:
            self.logger.error(f"读取文件失败: {e}")
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
