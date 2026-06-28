from app.content_regex_queue import (
    clear_queue,
    dequeue_by_message_id,
    enqueue_content_regex_items,
    get_content_regex_queue_size,
)


def test_dequeue_by_message_id_takes_contiguous_items() -> None:
    chat_id = "queue-test-contiguous"
    clear_queue(chat_id)
    enqueue_content_regex_items(
        chat_id,
        [
            {"messageId": "m1", "value": "a"},
            {"messageId": "m1", "value": "b"},
            {"messageId": "m2", "value": "c"},
        ],
    )

    message_id, items = dequeue_by_message_id(chat_id)

    assert message_id == "m1"
    assert [item["value"] for item in items] == ["a", "b"]
    assert get_content_regex_queue_size(chat_id) == 1
    clear_queue(chat_id)


def test_dequeue_by_message_id_handles_legacy_items() -> None:
    chat_id = "queue-test-legacy"
    clear_queue(chat_id)
    enqueue_content_regex_items(chat_id, [{"value": "legacy"}, {"messageId": "m1", "value": "next"}])

    message_id, items = dequeue_by_message_id(chat_id)

    assert message_id is None
    assert items == [{"value": "legacy"}]
    clear_queue(chat_id)


def test_queue_keeps_latest_500_items() -> None:
    chat_id = "queue-test-limit"
    clear_queue(chat_id)
    enqueue_content_regex_items(chat_id, [{"value": str(i)} for i in range(505)])

    assert get_content_regex_queue_size(chat_id) == 500
    message_id, items = dequeue_by_message_id(chat_id)
    assert message_id is None
    assert items[0]["value"] == "5"
    clear_queue(chat_id)
