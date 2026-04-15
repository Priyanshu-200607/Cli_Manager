from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from time import time
from typing import Any, Callable


Handler = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class EventBus:
    subscribers: dict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def publish(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        # wrap the raw payload with some standard routing info
        message = {
            "header": {
                "msg_id": str(uuid.uuid4()),
                "timestamp": time(),
                "source": payload.get("source", "event_bus"),
            },
            "event": topic,
            "payload": payload,
        }
        
        # safely grab a copy of the handlers so we don't hold the lock while calling them
        with self.lock:
            handlers = list(self.subscribers.get(topic, []))
            
        for handler in handlers:
            handler(message)
        return message

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        with self.lock:
            self.subscribers[topic].append(handler)

        def unsubscribe() -> None:
            # clean up the listener if they don't want to hear about it anymore
            with self.lock:
                if handler in self.subscribers.get(topic, []):
                    self.subscribers[topic].remove(handler)

        return unsubscribe
