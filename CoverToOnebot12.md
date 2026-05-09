# 花枫咖啡馆适配器与OneBot12协议的转换对照

## Ideaura特有事件类型

花枫咖啡馆（Allons）平台提供以下特有事件类型，可在消息处理中检测使用：

### 1. 普通消息
- **payload.type**: 消息的 `source_type` 为 `chatroom`、`topic` 或 `private`
- **说明**: 用户发送的普通消息（文本、图片、视频、文件、Markdown、HTML等）
- **转换后**: OneBot12 `message` 事件，`detail_type` 为 `private` 或 `group`

### 2. 消息编辑事件
- **eventType**: `edit`
- **说明**: 消息被编辑时触发
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `ideaura_message_edit`

### 3. 消息撤回事件
- **eventType**: `recall` 或 `messageType: "recalled"`
- **说明**: 消息被撤回时触发
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `ideaura_message_recall`

### 4. 消息转发事件
- **eventType**: `forward`
- **说明**: 消息被转发时触发
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `ideaura_message_forward`

### 5. 消息已读事件
- **eventType**: `read`
- **说明**: 消息被标记为已读时触发
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `ideaura_message_read`

### 6. 好友请求事件
- **payload.type**: `friend_request`
- **说明**: 收到好友请求、请求被接受或拒绝
- **转换后**: OneBot12 `request` 事件（`detail_type` 为 `friend`）或 `notice` 事件（`friend_increase`）

### 7. 好友事件
- **payload.type**: `friend_event`
- **说明**: 好友请求发送/接受/拒绝/删除
- **转换后**: OneBot12 `request`/`notice` 事件

### 8. 好友删除事件
- **payload.type**: `friend_removed`
- **说明**: 好友关系被解除
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `friend_decrease`

### 9. 好友在线状态事件
- **payload.type**: `friend_presence`
- **说明**: 好友上线或下线
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `ideaura_friend_online` 或 `ideaura_friend_offline`

### 10. 用户状态变更事件
- **payload.type**: `user_event`
- **说明**: 用户状态发生变化
- **转换后**: OneBot12 `notice` 事件，`detail_type` 为 `ideaura_user_status_change`

---

### 事件处理示例

```python
from ErisPulse.Core.Event import notice, message

# 处理普通消息
@message.on_message()
async def handle_message(event):
    if event.get_platform() == "ideaura":
        detail_type = event.get("detail_type")
        text = event.get_text()

        if detail_type == "group":
            source_type = event.get_source_type()
            if source_type == "chatroom":
                pass
            elif source_type == "topic":
                topic_name = event.get_topic_name()
                pass
        elif detail_type == "private":
            pass

# 处理通知事件（包括所有Ideaura特有事件）
@notice.on_notice()
async def handle_notice(event):
    if event.get_platform() != "ideaura":
        return

    detail_type = event.get("detail_type")

    if detail_type == "friend_increase":
        user_id = event.get_user_id()
        user_nickname = event.get_user_nickname()
        await event.reply("欢迎添加好友！")

    elif detail_type == "friend_decrease":
        user_id = event.get_user_id()

    elif detail_type == "ideaura_message_edit":
        message_id = event.get("message_id")
        new_content = event.get("ideaura_new_content", "")

    elif detail_type == "ideaura_message_recall":
        message_id = event.get("message_id")

    elif detail_type == "ideaura_message_forward":
        original_id = event.get("ideaura_original_message_id")
        forward_to = event.get("ideaura_forward_to")

    elif detail_type == "ideaura_friend_online":
        friend_id = event.get_user_id()
        friend_name = event.get_user_nickname()

    elif detail_type == "ideaura_friend_offline":
        friend_id = event.get_user_id()

    elif detail_type == "ideaura_user_status_change":
        status = event.get("ideaura_status")
        previous_status = event.get("ideaura_previous_status")
```

---

## 消息类型转换对照

### 1. 文本消息

原始事件:
```json
{
  "id": 1001,
  "topic_id": null,
  "user_id": "123",
  "content": "你好，这是一条测试消息",
  "created_at": "2026-05-09 22:00:00+08",
  "message_type": "normal",
  "message_subtype": "text",
  "source_type": "chatroom",
  "senderId": "123",
  "senderName": "张三",
  "senderAvatar": "https://example.com/avatar.jpg",
  "senderIsBot": false,
  "messageType": "normal",
  "messageSubtype": "text",
  "sourceType": "chatroom",
  "mentions": []
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "time": 1778338800.0,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "ideaura",
  "self": {
    "platform": "ideaura",
    "user_id": "21"
  },
  "ideaura_raw": { "...原始数据..." },
  "message_id": "1001",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "你好，这是一条测试消息"
      }
    }
  ],
  "alt_message": "你好，这是一条测试消息",
  "user_id": "123",
  "user_nickname": "张三",
  "group_id": "chatroom",
  "ideaura_source_type": "chatroom",
  "ideaura_sender_name": "张三",
  "ideaura_sender_avatar": "https://example.com/avatar.jpg",
  "ideaura_sender_is_bot": false,
  "ideaura_is_self": false,
  "ideaura_message_type": "normal",
  "ideaura_message_subtype": "text"
}
```

### 2. 图片消息

原始事件:
```json
{
  "id": 1002,
  "content": "这是一张图片",
  "message_subtype": "image",
  "source_type": "chatroom",
  "senderId": "123",
  "senderName": "张三",
  "fileInfo": {
    "url": "/uploads/photo.jpg",
    "name": "photo.jpg",
    "size": 123456,
    "type": "image/jpeg"
  },
  "mentions": []
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "time": 1778338800.0,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "ideaura",
  "self": {
    "platform": "ideaura",
    "user_id": "21"
  },
  "ideaura_raw": { "...原始数据..." },
  "message_id": "1002",
  "message": [
    {
      "type": "image",
      "data": {
        "file_id": "1002",
        "url": "/uploads/photo.jpg",
        "file_name": "photo.jpg",
        "size": 123456,
        "mime_type": "image/jpeg"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "这是一张图片"
      }
    }
  ],
  "alt_message": "[image:photo.jpg]这是一张图片",
  "user_id": "123",
  "user_nickname": "张三",
  "group_id": "chatroom",
  "ideaura_source_type": "chatroom",
  "ideaura_message_subtype": "image"
}
```

### 3. 视频消息

原始事件:
```json
{
  "id": 1003,
  "content": "",
  "message_subtype": "video",
  "source_type": "chatroom",
  "senderId": "123",
  "senderName": "张三",
  "fileInfo": {
    "url": "/uploads/video.mp4",
    "name": "video.mp4",
    "size": 5242880,
    "type": "video/mp4",
    "duration": 30
  },
  "mentions": []
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "message",
  "detail_type": "group",
  "platform": "ideaura",
  "message_id": "1003",
  "message": [
    {
      "type": "video",
      "data": {
        "file_id": "1003",
        "url": "/uploads/video.mp4",
        "file_name": "video.mp4",
        "size": 5242880,
        "mime_type": "video/mp4",
        "duration": 30
      }
    }
  ],
  "alt_message": "[video:video.mp4]",
  "user_id": "123",
  "user_nickname": "张三",
  "group_id": "chatroom"
}
```

### 4. 引用/回复消息

原始事件:
```json
{
  "id": 1004,
  "content": "我同意这个观点",
  "message_subtype": "text",
  "source_type": "chatroom",
  "senderId": "456",
  "senderName": "李四",
  "quotedMessageId": 1001,
  "quotedMessage": {
    "id": 1001,
    "content": "原始消息",
    "senderName": "张三"
  },
  "mentions": []
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "message",
  "detail_type": "group",
  "platform": "ideaura",
  "message_id": "1004",
  "message": [
    {
      "type": "reply",
      "data": {
        "message_id": "1001"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "我同意这个观点"
      }
    }
  ],
  "alt_message": "我同意这个观点",
  "user_id": "456",
  "user_nickname": "李四",
  "group_id": "chatroom"
}
```

### 5. 带@的消息

原始事件:
```json
{
  "id": 1005,
  "content": "请查看",
  "message_subtype": "text",
  "source_type": "chatroom",
  "senderId": "123",
  "senderName": "张三",
  "mentions": [
    {"type": "user", "id": "456", "nickname": "李四"},
    {"type": "all"}
  ]
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "message",
  "detail_type": "group",
  "platform": "ideaura",
  "message_id": "1005",
  "message": [
    {
      "type": "mention",
      "data": {
        "user_id": "456",
        "user_name": "李四"
      }
    },
    {
      "type": "mention_all",
      "data": {}
    },
    {
      "type": "text",
      "data": {
        "text": "请查看"
      }
    }
  ],
  "alt_message": "请查看",
  "user_id": "123",
  "user_nickname": "张三",
  "group_id": "chatroom"
}
```

### 6. 转发消息

原始事件:
```json
{
  "id": 1006,
  "content": "[转发自 张三]: 原始消息内容",
  "message_type": "forwarded",
  "forward_source_id": 1001,
  "source_type": "chatroom",
  "senderId": "456",
  "originalMessageId": 1001
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "message",
  "detail_type": "group",
  "platform": "ideaura",
  "message_id": "1006",
  "message": [
    {
      "type": "ideaura_forwarded",
      "data": {
        "forward_source_id": "1001",
        "original_message_id": "1001"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "[转发自 张三]: 原始消息内容"
      }
    }
  ],
  "user_id": "456",
  "group_id": "chatroom",
  "ideaura_message_type": "forwarded"
}
```

### 7. 撤回消息事件

原始事件:
```json
{
  "id": 1007,
  "isRecalled": true,
  "recallTime": "2026-05-09 22:10:00+08",
  "messageType": "recalled",
  "senderId": "123",
  "senderName": "张三",
  "source_type": "chatroom"
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "notice",
  "detail_type": "ideaura_message_recall",
  "platform": "ideaura",
  "message_id": "1007",
  "user_id": "123",
  "user_nickname": "张三",
  "group_id": "chatroom",
  "ideaura_source_type": "chatroom",
  "ideaura_recall_time": "2026-05-09 22:10:00+08",
  "ideaura_is_self": false
}
```

### 8. 好友请求事件

原始事件:
```json
{
  "type": "friend_request",
  "eventType": "new_request",
  "fromUserId": "456",
  "fromUserName": "李四",
  "requestId": "789",
  "message": "你好，我想加你为好友"
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "request",
  "detail_type": "friend",
  "platform": "ideaura",
  "user_id": "456",
  "user_nickname": "李四",
  "ideaura_request_id": "789",
  "ideaura_message": "你好，我想加你为好友"
}
```

### 9. 好友上线事件

原始事件:
```json
{
  "type": "friend_presence",
  "eventType": "friend_online",
  "friendId": 456,
  "friendName": "李四",
  "friendAvatar": "https://example.com/avatar.jpg",
  "timestamp": "2026-05-09T15:00:00.000Z"
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "notice",
  "detail_type": "ideaura_friend_online",
  "platform": "ideaura",
  "user_id": "456",
  "user_nickname": "李四",
  "ideaura_friend_avatar": "https://example.com/avatar.jpg",
  "ideaura_presence_status": "online"
}
```

### 10. 私聊消息

原始事件:
```json
{
  "id": 2001,
  "sender_id": "123",
  "receiver_id": "456",
  "content": "你好，这是私聊消息",
  "message_subtype": "text",
  "source_type": "private",
  "senderId": "123",
  "senderName": "张三",
  "receiverId": "456",
  "receiverName": "李四",
  "isSelf": false
}
```
转换后:
```json
{
  "id": "uuid-generated",
  "type": "message",
  "detail_type": "private",
  "platform": "ideaura",
  "message_id": "2001",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "你好，这是私聊消息"
      }
    }
  ],
  "alt_message": "你好，这是私聊消息",
  "user_id": "123",
  "user_nickname": "张三",
  "ideaura_source_type": "private",
  "ideaura_is_self": false
}
```

> **注意**: 自身发送的消息（`isSelf: true`）会被过滤器自动忽略，不会产生事件。

---

## Ideaura发送消息类型（OneBot12扩展）

Ideaura适配器支持使用 OneBot12 消息段格式发送消息，支持以下类型：

### 1. 基础消息类型

| 类型 | 说明 | 参数 |
|------|------|------|
| `text` | 纯文本 | `text`: 文本内容 |
| `ideaura_markdown` | Markdown格式 | `markdown`: Markdown代码 |
| `ideaura_html` | HTML格式 | `html`: HTML代码 |

### 2. 媒体消息类型

| 类型 | 说明 | 参数 |
|------|------|------|
| `image` | 图片 | `file`: 文件bytes/URL/本地路径, `filename`: 文件名 |
| `video` | 视频 | `file`: 文件bytes/URL/本地路径, `filename`: 文件名 |
| `file` | 文件 | `file`: 文件bytes/URL/本地路径, `filename`: 文件名 |

### 3. Ideaura特有类型

| 类型 | 说明 | 参数 |
|------|------|------|
| `reply` | 回复消息 | `message_id`: 消息ID |
| `mention` | @用户 | `user_id`: 用户ID |
| `mention_all` | @全体 | 无参数 |

### 4. 使用链式调用发送

```python
# 基础发送
await ideaura.Send.To("group", "chatroom").Text("Hello")

# 发送带@的消息
await ideaura.Send.To("group", "chatroom").At("456").Text("@李四 你好")

# @多个用户
await ideaura.Send.To("group", "chatroom").At("456").At("789").Text("@多人")

# 发送回复消息
await ideaura.Send.To("group", "chatroom").Reply("1001").Text("回复内容")

# 发送到话题
await ideaura.Send.To("group", "789").Text("话题消息")

# 发送私聊消息
await ideaura.Send.To("user", "456").Text("私聊消息")

# 组合使用
await ideaura.Send.To("group", "chatroom").Reply("1001").At("456").Text("回复并@")

# 使用 Raw_ob12 发送复杂消息
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "http://example.com/img.jpg"}},
    {"type": "text", "data": {"text": "第二行"}}
]
await ideaura.Send.To("group", "chatroom").Raw_ob12(message)
```

### 5. 消息操作

```python
# 撤回消息
await ideaura.Send.To("group", "chatroom").Recall("message_id")

# 编辑消息
await ideaura.Send.To("group", "chatroom").Edit("message_id", "新内容")
```

### 6. 发送媒体文件

```python
# 从本地文件发送图片
with open("photo.jpg", "rb") as f:
    image_data = f.read()
await ideaura.Send.To("group", "chatroom").Image(image_data)

# 从URL发送图片
await ideaura.Send.To("group", "chatroom").Image("https://example.com/photo.jpg")

# 发送视频
await ideaura.Send.To("group", "chatroom").Video("https://example.com/video.mp4")

# 发送文件（带文件名）
with open("doc.pdf", "rb") as f:
    file_data = f.read()
await ideaura.Send.To("group", "chatroom").File(file_data, "文档.pdf")

# 发送Markdown
await ideaura.Send.To("group", "chatroom").Markdown("# 标题\n- 列表项")

# 发送HTML
await ideaura.Send.To("group", "chatroom").Html("<b>加粗</b>消息")
```
