import time
import random

RETRY_PROFILE = [1, 2, 4, 8, 15, 30]
MAX_RETRY = 30

class RetryManager:
    def __init__(self, logger):
        self.logger = logger
        self.attempts = 0

    def next_delay(self) -> float:
        if self.attempts < len(RETRY_PROFILE):
            base = RETRY_PROFILE[self.attempts]
        else:
            base = MAX_RETRY
            
        jitter = random.uniform(0, 0.2) * base
        delay = base + jitter
        
        self.attempts += 1
        return delay

    def reset(self):
        self.attempts = 0

    async def wait(self):
        import asyncio
        delay = self.next_delay()
        self.logger.info("retry.scheduled", detail=f"Waiting {delay:.2f}s before retry", attempt=self.attempts)
        await asyncio.sleep(delay)
        
    def wait_sync(self):
        delay = self.next_delay()
        self.logger.info("retry.scheduled", detail=f"Waiting {delay:.2f}s before retry", attempt=self.attempts)
        time.sleep(delay)
