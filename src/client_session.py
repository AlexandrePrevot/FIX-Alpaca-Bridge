import queue
import threading


class ClientSession:

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.queue: queue.Queue = queue.Queue()

        # one consumer = one thread
        # might not scale
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()

    def _consume(self):
        while True:
            data = self.queue.get()
            if data is None:
                break
            print(f"[{self.client_id}] {data}")

    def stop(self):
        self.queue.put(None)
        self._thread.join(timeout=5)
