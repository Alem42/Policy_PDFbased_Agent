class DatabaseStatus:
    def __init__(self) -> None:
        self.status = "disabled"

    async def connect(self) -> None:
        self.status = "connected"

    async def disconnect(self) -> None:
        self.status = "disconnected"


database = DatabaseStatus()
