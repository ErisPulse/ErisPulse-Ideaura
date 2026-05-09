# IdeauraAdapter 模块文档

## 简介
IdeauraAdapter 是基于 [ErisPulse](https://github.com/ErisPulse/ErisPulse/) 架构的花枫咖啡馆（Allons）协议适配器，整合了所有平台功能模块，提供统一的事件处理和消息操作接口。

## 使用示例

### OneBot12标准事件类型

Ideaura适配器完全兼容 OneBot12 标准事件格式，并提供了一些扩展字段：

| 事件类型 | detail_type | 说明 |
|----------|-------------|------|
| 消息事件 | message | 标准消息事件 |
| 好友增加 | notice.friend_increase | 好友请求被接受 |
| 好友减少 | notice.friend_decrease | 好友关系被解除 |
| 消息编辑 | notice.ideaura_message_edit | 消息被编辑 |
| 消息撤回 | notice.ideaura_message_recall | 消息被撤回 |
| 消息转发 | notice.ideaura_message_forward | 消息被转发 |
| 消息已读 | notice.ideaura_message_read | 消息被标记已读 |
| 好友被拒 | notice.ideaura_friend_rejected | 好友请求被拒绝 |
| 好友上线 | notice.ideaura_friend_online | 好友上线 |
| 好友下线 | notice.ideaura_friend_offline | 好友下线 |
| 用户状态变更 | notice.ideaura_user_status_change | 用户状态变化 |
| 好友请求 | request.friend | 收到好友请求 |

---

## 消息发送示例

```python
from ErisPulse.Core import adapter
ideaura = adapter.get("ideaura")

# 发送文本消息
await ideaura.Send.To("user", "user_id").Text("Hello World!")

# 发送带@的消息
await ideaura.Send.To("group", "chatroom").At("456").Text("@李四 你好")

# @多人
await ideaura.Send.To("group", "chatroom").At("456").At("789").Text("@多人")

# @全体
await ideaura.Send.To("group", "chatroom").AtAll().Text("通知所有人")

# 发送回复消息
await ideaura.Send.To("group", "chatroom").Reply("1001").Text("回复内容")

# 发送图片（从本地文件）
with open("photo.jpg", "rb") as f:
    image_data = f.read()
await ideaura.Send.To("group", "chatroom").Image(image_data)

# 发送图片（从URL）
await ideaura.Send.To("group", "chatroom").Image("https://example.com/photo.jpg")

# 发送视频
await ideaura.Send.To("group", "chatroom").Video("https://example.com/video.mp4")

# 发送文件（带文件名）
with open("doc.pdf", "rb") as f:
    file_data = f.read()
await ideaura.Send.To("group", "chatroom").File(file_data, "文档.pdf")

# 发送 Markdown 格式消息
await ideaura.Send.To("group", "chatroom").Markdown("# 标题\n- 列表项")

# 发送 HTML 格式消息
await ideaura.Send.To("group", "chatroom").Html("<b>加粗</b>消息")

# 编辑消息
await ideaura.Send.To("group", "chatroom").Edit("message_id", "修改后的内容")

# 撤回消息
await ideaura.Send.To("group", "chatroom").Recall("message_id")

# 使用 Raw_ob12 发送复杂消息
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "http://example.com/img.jpg"}},
    {"type": "text", "data": {"text": "第二行"}}
]
await ideaura.Send.To("group", "chatroom").Raw_ob12(message)

# 组合使用
await ideaura.Send.To("group", "chatroom").Reply("1001").At("456").Text("回复并@")
```

---

### 配置说明

首次运行会生成配置。Ideaura适配器支持多账户配置。

#### 首次运行生成的默认配置

```toml
[IdeauraAdapter.accounts.default]
email = ""            # 登录邮箱（必填，请修改为实际邮箱）
password = ""         # 登录密码（必填，请修改为实际密码）
enabled = false       # 是否启用（填写完账号密码后改为true）
```

#### 多账户配置示例

```toml
# 账户1
[IdeauraAdapter.accounts.bot1]
email = "bot1@example.com"
password = "password1"
enabled = true

# 账户2
[IdeauraAdapter.accounts.bot2]
email = "bot2@example.com"
password = "password2"
enabled = true

# 可选：自定义服务器地址
[IdeauraAdapter]
base_url = "https://api-cofe.allons-y.uk:3009"
ws_url = "wss://api-cofe.allons-y.uk:3009/mqtt"
heartbeat_interval = 30
```

**配置项说明：**
- `email`：账户登录邮箱（必填）
- `password`：账户登录密码（必填）
- `enabled`：是否启用该账户（可选，默认为true）

**全局配置项：**
- `base_url`：API 服务器地址（可选，默认为花枫咖啡馆官方地址）
- `ws_url`：WebSocket 服务器地址（可选，默认为花枫咖啡馆官方地址）
- `heartbeat_interval`：心跳间隔秒数（可选，默认30秒）

#### 指定发送账户

可以通过 `Using()` 方法指定使用哪个账户发送消息：

```python
from ErisPulse.Core import adapter
ideaura = adapter.get("ideaura")

# 使用账户名发送消息
await ideaura.Send.Using("bot1").To("user", "user123").Text("Hello from bot1!")

# 使用 user_id 发送消息（自动匹配对应账户）
await ideaura.Send.Using("456").To("group", "chatroom").Text("Hello from bot2!")

# 不指定时使用第一个启用的账户
await ideaura.Send.To("user", "user123").Text("Hello from default account!")
```

---

## 平台特有功能

请参考 [平台特性文档](platform-features.md) 了解花枫咖啡馆平台的特有功能，包括特有事件类型、扩展字段说明、消息编辑事件、消息转发事件、好友在线状态事件、用户状态变更事件等内容。

## 事件监听示例

### 使用 Event 模块（推荐）

```python
from ErisPulse.Core.Event import message, notice

@message.on_message()
async def handle_message(event):
    if event["platform"] == "ideaura":
        detail_type = event.get("detail_type")
        text = event.get_text()
        
        if detail_type == "group":
            source_type = event.get("ideaura_source_type")
            if source_type == "topic":
                topic_name = event.get("ideaura_topic_name")
        elif detail_type == "private":
            pass

@notice.on_notice()
async def handle_notice(event):
    if event["platform"] == "ideaura":
        detail_type = event.get("detail_type")
        
        if detail_type == "ideaura_message_edit":
            new_content = event.get("ideaura_new_content", "")
            
        elif detail_type == "ideaura_message_recall":
            message_id = event.get("message_id")
            
        elif detail_type == "ideaura_friend_online":
            friend_name = event.get_user_nickname()
```

### 使用 OneBot12 标准事件

```python
from ErisPulse import sdk

@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "ideaura":
        user_id = event["self"]["user_id"]
        print(f"消息来自账户: {user_id}")

@sdk.adapter.on("notice")
async def handle_notice(event):
    if event["platform"] == "ideaura":
        pass

@sdk.adapter.on("request")
async def handle_request(event):
    if event["platform"] == "ideaura":
        if event.get("detail_type") == "friend":
            user_nickname = event.get("user_nickname")
            message = event.get("ideaura_message", "")
```

## 注意事项

1. 确保在调用 `startup()` 前完成所有处理器的注册
2. 适配器使用 WebSocket 长连接接收事件，支持自动重连（固定5秒延迟）
3. 二进制内容（图片/视频等）支持 bytes、URL、本地路径三种输入方式
4. 文件大小限制为 10MB
5. 自身发送的消息（`isSelf: true`）会被自动过滤，不会产生事件
6. @全体（`AtAll()`）需要管理员权限
7. 程序退出时请调用 `shutdown()` 确保资源释放

---

### 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [花枫咖啡馆](https://cofe.allons-y.uk/)
- [OneBot12协议对照](CoverToOnebot12.md)
