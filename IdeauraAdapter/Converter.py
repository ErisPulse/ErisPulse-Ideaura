import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional


class IdeauraConverter:
    def __init__(self):
        self._setup_event_mapping()

    def _setup_event_mapping(self):
        self.message_event_map = {
            "edit": "ideaura_message_edit",
            "recall": "ideaura_message_recall",
            "forward": "ideaura_message_forward",
            "read": "ideaura_message_read",
        }
        self.friend_request_map = {
            "new_request": ("request", "friend"),
            "accepted": ("notice", "friend_increase"),
            "rejected": ("notice", "ideaura_friend_rejected"),
        }
        self.friend_presence_map = {
            "friend_online": "ideaura_friend_online",
            "friend_offline": "ideaura_friend_offline",
        }

    def convert(self, data: Dict, self_user_id: str = None) -> Optional[Dict]:
        if not isinstance(data, dict):
            return None

        payload_type = data.get("type", "")
        event_type = data.get("eventType", data.get("subtype", ""))
        message_type = data.get("messageType", data.get("message_type", ""))

        base_event = {
            "id": str(uuid.uuid4()),
            "time": self._parse_time(data.get("created_at", data.get("timestamp", data.get("createdAt")))),
            "type": "",
            "detail_type": "",
            "sub_type": "",
            "platform": "ideaura",
            "self": {
                "platform": "ideaura",
                "user_id": self_user_id or "",
            },
            "ideaura_raw": data,
            "ideaura_raw_type": payload_type or message_type,
        }

        if payload_type == "message_event":
            return self._handle_message_event(event_type, data, base_event)
        elif payload_type == "friend_request":
            return self._handle_friend_request(event_type, data, base_event)
        elif payload_type == "friend_event":
            return self._handle_friend_event(event_type, data, base_event)
        elif payload_type == "friend_removed":
            return self._handle_friend_removed(data, base_event)
        elif payload_type == "friend_presence":
            return self._handle_friend_presence(event_type, data, base_event)
        elif payload_type == "user_event":
            return self._handle_user_event(event_type, data, base_event)
        else:
            source_type = data.get("source_type", data.get("sourceType", ""))
            is_recalled = data.get("isRecalled", False) or message_type == "recalled"

            if is_recalled:
                return self._handle_recalled_message(data, base_event)
            elif source_type in ("chatroom", "topic", "private") or message_type in ("normal", "edited", "forwarded", "quoted"):
                return self._handle_incoming_message(data, base_event, self_user_id)

        return None

    def _parse_time(self, ts) -> float:
        if ts is None:
            return time.time()
        if isinstance(ts, (int, float)):
            return ts / 1000 if ts > 1e12 else ts
        if isinstance(ts, str):
            try:
                cleaned = ts.replace("Z", "+00:00")
                if "+" in cleaned and len(cleaned.split("+")[-1]) <= 2:
                    cleaned += ":00"
                dt = datetime.fromisoformat(cleaned)
                return dt.timestamp()
            except Exception:
                pass
        return time.time()

    def _resolve_user_id(self, data: Dict, self_user_id: str = None) -> str:
        source_type = data.get("source_type", data.get("sourceType", ""))
        if source_type == "private":
            is_self = data.get("isSelf", False)
            sender_id = str(data.get("sender_id", data.get("senderId", "")))
            receiver_id = str(data.get("receiver_id", data.get("receiverId", "")))
            if is_self:
                return receiver_id
            return sender_id
        return str(data.get("user_id", data.get("userId", data.get("senderId", ""))))

    def _should_filter_self(self, data: Dict, self_user_id: str = None) -> bool:
        if not self_user_id:
            return False
        is_self = data.get("isSelf", False)
        if is_self:
            return True
        return False

    def _handle_incoming_message(self, data: Dict, base_event: Dict, self_user_id: str = None) -> Optional[Dict]:
        if self._should_filter_self(data, self_user_id):
            return None

        source_type = data.get("source_type", data.get("sourceType", ""))
        message_type = data.get("message_type", data.get("messageType", "normal"))
        message_subtype = data.get("message_subtype", data.get("messageSubtype", "text"))
        content = data.get("content", "")
        user_id = self._resolve_user_id(data, self_user_id)
        topic_id = data.get("topic_id", data.get("topicId"))
        message_id = str(data.get("id", data.get("messageId", data.get("message_id", ""))))
        quoted_message_id = data.get("quoted_message_id", data.get("quotedMessageId"))
        forward_source_id = data.get("forward_source_id", data.get("forwardSourceId"))
        original_message_id = data.get("originalMessageId", data.get("original_message_id"))
        mentions_raw = data.get("mentions", [])
        file_info = data.get("fileInfo")

        sender_name = data.get("senderName", data.get("nickname", data.get("username", "")))
        sender_avatar = data.get("senderAvatar", "")
        sender_is_bot = data.get("senderIsBot", False)

        base_event["time"] = self._parse_time(data.get("created_at", data.get("timestamp")))

        detail_type = "private" if source_type == "private" else "group"

        base_event.update({
            "type": "message",
            "detail_type": detail_type,
            "message_id": message_id,
            "user_id": user_id,
            "user_nickname": sender_name,
        })

        if detail_type == "group":
            if source_type == "chatroom" or (not topic_id and source_type != "topic"):
                base_event["group_id"] = "chatroom"
            else:
                base_event["group_id"] = str(topic_id) if topic_id else "chatroom"

        message_segments = []
        alt_parts = []

        mention_segments = self._parse_mentions(mentions_raw)

        if quoted_message_id:
            message_segments.append({
                "type": "reply",
                "data": {"message_id": str(quoted_message_id)},
            })

        if message_type == "forwarded" or forward_source_id:
            fwd_data = {"forward_source_id": str(forward_source_id or original_message_id or "")}
            if original_message_id:
                fwd_data["original_message_id"] = str(original_message_id)
            message_segments.append({
                "type": "ideaura_forwarded",
                "data": fwd_data,
            })

        if message_type == "edited":
            edit_history = data.get("editHistory", [])
            message_segments.append({
                "type": "ideaura_edited",
                "data": {
                    "updated_at": data.get("updated_at"),
                    "edit_history": edit_history,
                },
            })

        if file_info and isinstance(file_info, dict) and file_info.get("url"):
            media_type = self._detect_media_type(file_info, message_subtype)
            media_data = {
                "file_id": message_id,
                "url": file_info.get("url", ""),
                "file_name": file_info.get("name", ""),
                "size": file_info.get("size", 0),
                "mime_type": file_info.get("type", ""),
            }
            if file_info.get("width"):
                media_data["width"] = file_info["width"]
            if file_info.get("height"):
                media_data["height"] = file_info["height"]
            if file_info.get("duration"):
                media_data["duration"] = file_info["duration"]
            if file_info.get("thumbnail"):
                media_data["thumbnail"] = file_info["thumbnail"]

            message_segments.append({"type": media_type, "data": media_data})
            alt_parts.append(f"[{media_type}:{file_info.get('name', '')}]")

            if content:
                message_segments.append({"type": "text", "data": {"text": content}})
                alt_parts.append(content)
        elif message_subtype == "markdown":
            text = content if isinstance(content, str) else str(content)
            if text:
                message_segments.append({"type": "text", "data": {"text": text}})
                message_segments.append({"type": "ideaura_markdown", "data": {"markdown": text}})
                alt_parts.append(text)
        elif message_subtype == "html":
            text = content if isinstance(content, str) else str(content)
            if text:
                message_segments.append({"type": "text", "data": {"text": text}})
                message_segments.append({"type": "ideaura_html", "data": {"html": text}})
                alt_parts.append(text)
        else:
            text = content if isinstance(content, str) else str(content) if content else ""
            if text:
                message_segments.append({"type": "text", "data": {"text": text}})
                alt_parts.append(text)

        message_segments = mention_segments + message_segments

        if not message_segments:
            message_segments.append({"type": "text", "data": {"text": str(content) if content else ""}})

        base_event["message"] = message_segments
        base_event["alt_message"] = "".join(alt_parts) or "[消息]"

        base_event["ideaura_source_type"] = source_type
        base_event["ideaura_sender_name"] = sender_name
        base_event["ideaura_sender_avatar"] = sender_avatar
        base_event["ideaura_sender_is_bot"] = sender_is_bot
        base_event["ideaura_is_self"] = data.get("isSelf", False)
        base_event["ideaura_topic_name"] = data.get("topicName", "")
        base_event["ideaura_message_type"] = message_type
        base_event["ideaura_message_subtype"] = message_subtype

        return base_event

    def _parse_mentions(self, mentions_raw) -> list:
        segments = []
        if not mentions_raw or not isinstance(mentions_raw, list):
            return segments
        for m in mentions_raw:
            if isinstance(m, str):
                segments.append({
                    "type": "mention",
                    "data": {"user_id": m},
                })
            elif isinstance(m, dict):
                mention_type = m.get("type", "user")
                if mention_type == "all":
                    segments.append({
                        "type": "mention_all",
                        "data": {},
                    })
                else:
                    uid = str(m.get("id", m.get("user_id", "")))
                    if uid:
                        segments.append({
                            "type": "mention",
                            "data": {
                                "user_id": uid,
                                "user_name": m.get("nickname", m.get("username", m.get("name", ""))),
                            },
                        })
        return segments

    def _detect_media_type(self, file_info: Dict, subtype: str) -> str:
        if subtype in ("image", "video", "file"):
            return subtype
        mime = file_info.get("type", "")
        if mime.startswith("image/"):
            return "image"
        elif mime.startswith("video/"):
            return "video"
        return "file"

    def _handle_recalled_message(self, data: Dict, base_event: Dict) -> Dict:
        message_id = str(data.get("id", data.get("messageId", "")))
        user_id = str(data.get("senderId", data.get("user_id", data.get("userId", ""))))
        source_type = data.get("source_type", data.get("sourceType", ""))
        topic_id = data.get("topic_id", data.get("topicId"))

        base_event.update({
            "type": "notice",
            "detail_type": "ideaura_message_recall",
            "message_id": message_id,
            "user_id": user_id,
            "user_nickname": data.get("senderName", ""),
        })

        if source_type == "private":
            pass
        elif source_type == "chatroom":
            base_event["group_id"] = "chatroom"
        elif source_type == "topic" or topic_id:
            base_event["group_id"] = str(topic_id) if topic_id else "chatroom"
        else:
            base_event["group_id"] = "chatroom"

        base_event["ideaura_source_type"] = source_type
        base_event["ideaura_recall_time"] = data.get("recallTime", "")
        base_event["ideaura_is_self"] = data.get("isSelf", False)

        return base_event

    def _handle_message_event(self, event_type: str, data: Dict, base_event: Dict) -> Optional[Dict]:
        mapped = self.message_event_map.get(event_type)
        if not mapped:
            return None

        base_event.update({
            "type": "notice",
            "detail_type": mapped,
        })

        message_id = data.get("messageId", data.get("message_id", ""))
        if message_id:
            base_event["message_id"] = str(message_id)

        sender_id = data.get("userId", data.get("senderId", data.get("user_id", data.get("forwarderId", ""))))
        if sender_id:
            base_event["user_id"] = str(sender_id)

        source_type = data.get("sourceType", data.get("source_type", ""))
        topic_id = data.get("topicId", data.get("topic_id"))

        if source_type == "private":
            target_user_id = data.get("targetUserId", "")
            if target_user_id:
                base_event["ideaura_target_user_id"] = str(target_user_id)
        elif source_type == "topic" or topic_id:
            base_event["group_id"] = str(topic_id) if topic_id else "chatroom"
        elif source_type == "chatroom":
            base_event["group_id"] = "chatroom"

        if event_type == "edit":
            base_event["ideaura_new_content"] = data.get("content", "")
            updated_msg = data.get("updatedMessage", {})
            if updated_msg:
                base_event["ideaura_updated_message"] = updated_msg
        elif event_type == "recall":
            base_event["ideaura_is_recalled"] = data.get("isRecalled", True)
        elif event_type == "forward":
            base_event["ideaura_forward_to"] = data.get("targetTopicId", "")
            base_event["ideaura_original_message_id"] = str(data.get("originalMessageId", ""))
            base_event["ideaura_forwarded_message_id"] = str(data.get("forwardedMessageId", ""))
            forwarder_name = data.get("forwarderName", "")
            if forwarder_name:
                base_event["user_nickname"] = forwarder_name
        elif event_type == "read":
            base_event["ideaura_reader_id"] = str(data.get("readerId", ""))
            base_event["ideaura_reader_name"] = data.get("readerName", "")

        base_event["ideaura_source_type"] = source_type
        base_event["ideaura_is_self"] = data.get("isSelf", False)

        return base_event

    def _handle_friend_request(self, subtype: str, data: Dict, base_event: Dict) -> Optional[Dict]:
        mapped = self.friend_request_map.get(subtype)
        if not mapped:
            return None

        event_type, detail_type = mapped

        base_event.update({
            "type": event_type,
            "detail_type": detail_type,
        })

        if subtype == "new_request":
            base_event["user_id"] = str(data.get("fromUserId", data.get("senderId", "")))
            base_event["user_nickname"] = data.get("fromUserName", data.get("senderName", ""))
            base_event["ideaura_request_id"] = str(data.get("requestId", ""))
            base_event["ideaura_message"] = data.get("message", "")
        elif subtype == "accepted":
            base_event["user_id"] = str(data.get("accepterId", ""))
            base_event["user_nickname"] = data.get("accepterName", "")
            base_event["ideaura_request_id"] = str(data.get("requestId", ""))
            base_event["ideaura_requester_id"] = str(data.get("requesterId", ""))
            base_event["ideaura_requester_name"] = data.get("requesterName", "")
            base_event["ideaura_friendship_id"] = str(data.get("friendshipId", ""))
        elif subtype == "rejected":
            base_event["user_id"] = str(data.get("rejecterId", ""))
            base_event["user_nickname"] = data.get("rejecterName", "")
            base_event["ideaura_request_id"] = str(data.get("requestId", ""))
            base_event["ideaura_requester_id"] = str(data.get("requesterId", ""))
            base_event["ideaura_requester_name"] = data.get("requesterName", "")

        return base_event

    def _handle_friend_event(self, event_type: str, data: Dict, base_event: Dict) -> Optional[Dict]:
        event_map = {
            "request_sent": ("request", "friend"),
            "request_accepted": ("notice", "friend_increase"),
            "request_rejected": ("notice", "ideaura_friend_rejected"),
            "removed": ("notice", "friend_decrease"),
        }

        mapped = event_map.get(event_type)
        if not mapped:
            return None

        event_type_ob, detail_type = mapped

        base_event.update({
            "type": event_type_ob,
            "detail_type": detail_type,
        })

        if event_type == "request_sent":
            base_event["user_id"] = str(data.get("senderId", ""))
            base_event["user_nickname"] = data.get("senderName", "")
            base_event["ideaura_request_id"] = str(data.get("requestId", ""))
            base_event["ideaura_target_user_id"] = str(data.get("receiverId", ""))
            base_event["ideaura_target_user_name"] = data.get("receiverName", "")
            base_event["ideaura_message"] = data.get("message", "")
        elif event_type == "request_accepted":
            base_event["user_id"] = str(data.get("accepterId", ""))
            base_event["user_nickname"] = data.get("accepterName", "")
            base_event["ideaura_request_id"] = str(data.get("requestId", ""))
            base_event["ideaura_requester_id"] = str(data.get("requesterId", ""))
            base_event["ideaura_requester_name"] = data.get("requesterName", "")
            base_event["ideaura_friendship_id"] = str(data.get("friendshipId", ""))
        elif event_type == "request_rejected":
            base_event["user_id"] = str(data.get("rejecterId", ""))
            base_event["user_nickname"] = data.get("rejecterName", "")
            base_event["ideaura_request_id"] = str(data.get("requestId", ""))
            base_event["ideaura_requester_id"] = str(data.get("requesterId", ""))
            base_event["ideaura_requester_name"] = data.get("requesterName", "")
        elif event_type == "removed":
            base_event["user_id"] = str(data.get("removerId", ""))
            base_event["user_nickname"] = data.get("removerName", "")
            base_event["ideaura_removed_user_id"] = str(data.get("removedUserId", data.get("removedId", "")))
            base_event["ideaura_removed_user_name"] = data.get("removedUserName", data.get("removedName", ""))

        return base_event

    def _handle_friend_removed(self, data: Dict, base_event: Dict) -> Optional[Dict]:
        base_event.update({
            "type": "notice",
            "detail_type": "friend_decrease",
            "user_id": str(data.get("removerId", "")),
            "user_nickname": data.get("removerName", ""),
        })

        base_event["ideaura_removed_user_id"] = str(data.get("removedId", data.get("removedUserId", "")))
        base_event["ideaura_removed_user_name"] = data.get("removedName", data.get("removedUserName", ""))

        return base_event

    def _handle_friend_presence(self, event_type: str, data: Dict, base_event: Dict) -> Optional[Dict]:
        mapped = self.friend_presence_map.get(event_type)
        if not mapped:
            return None

        base_event.update({
            "type": "notice",
            "detail_type": mapped,
            "user_id": str(data.get("friendId", "")),
            "user_nickname": data.get("friendName", ""),
        })

        base_event["ideaura_friend_avatar"] = data.get("friendAvatar", "")
        base_event["ideaura_presence_status"] = "online" if event_type == "friend_online" else "offline"

        return base_event

    def _handle_user_event(self, event_type: str, data: Dict, base_event: Dict) -> Optional[Dict]:
        if event_type != "status_change":
            return None

        base_event.update({
            "type": "notice",
            "detail_type": "ideaura_user_status_change",
            "user_id": str(data.get("userId", data.get("user_id", ""))),
            "user_nickname": data.get("username", ""),
        })

        base_event["ideaura_status"] = data.get("status", "")
        base_event["ideaura_previous_status"] = data.get("previous_status", data.get("previousStatus", ""))

        return base_event
