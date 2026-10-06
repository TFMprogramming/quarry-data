"""A cap on optional SEC requests per run, so catching up on history never
pushes the daily job past its time limit. Missing work continues next run."""


class Budget:
    def __init__(self, requests: int):
        self.remaining = requests

    def allows(self, count: int = 1) -> bool:
        return self.remaining >= count

    def spend(self, count: int = 1) -> None:
        self.remaining -= count
