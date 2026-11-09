"""request 事件标准 request_id 字段测试（顶层 request_id 与 ideaura_request_id 同值）"""

from IdeauraAdapter.Converter import IdeauraConverter


def test_friend_request_has_standard_request_id():
    data = {
        "type": "friend_request",
        "eventType": "new_request",
        "requestId": "req_1",
        "fromUserId": "u1",
        "fromUserName": "A",
        "message": "hi",
    }
    event = IdeauraConverter().convert(data)
    assert event is not None
    assert event["type"] == "request"
    assert event["detail_type"] == "friend"
    assert event["request_id"] == "req_1"
    assert event["ideaura_request_id"] == "req_1"


def test_friend_event_request_sent_has_request_id():
    data = {
        "type": "friend_event",
        "eventType": "request_sent",
        "requestId": "req_2",
        "senderId": "u1",
        "senderName": "A",
        "receiverId": "u2",
    }
    event = IdeauraConverter().convert(data)
    assert event is not None
    assert event["type"] == "request"
    assert event["request_id"] == "req_2"
    assert event["ideaura_request_id"] == "req_2"
