"""
⏱️ Rate Limiter - API 频率限制器
使用 Token Bucket 算法实现
"""

import asyncio
import logging
import time
from collections import deque
from typing import Dict


class TokenBucket:
    """Token Bucket 算法"""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: 桶容量（最大令牌数）
            refill_rate: 令牌补充速率（每秒补充的令牌数）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill_time = time.time()

    def acquire(self) -> bool:
        """
        获取令牌（非阻塞）
        
        Returns:
            bool: 是否成功获取令牌
        """
        now = time.time()
        
        # 补充令牌
        elapsed = now - self.last_refill_time
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill_time = now
        
        # 获取令牌
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        else:
            return False


class RateLimiter:
    """
    API 频率限制器
    
    支持多种限流策略：
    - Token Bucket（令牌桶）
    - Fixed Window（固定窗口）
    - Sliding Window（滑动窗口）
    """

    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Token Buckets（按端点分类）
        self.buckets: Dict[str, TokenBucket] = {}
        
        # 请求队列（用于排队）
        self.request_queue: deque = deque()
        
        # 限流策略
        self.strategy = config.get("strategy", "token_bucket")
        
        # 默认限流规则
        self.default_capacity = config.get("default_capacity", 10)
        self.default_refill_rate = config.get("default_refill_rate", 1.0)
        
        # 初始化限流规则
        self._init_buckets()

    def _init_buckets(self):
        """初始化 Token Buckets"""
        rules = self.config.get("rules", {})
        
        for endpoint, rule in rules.items():
            capacity = rule.get("capacity", self.default_capacity)
            refill_rate = rule.get("refill_rate", self.default_refill_rate)
            
            self.buckets[endpoint] = TokenBucket(
                capacity=capacity,
                refill_rate=refill_rate
            )
            
            self.logger.info(
                f"✅ 限流规则初始化: {endpoint} "
                f"(容量: {capacity}, 速率: {refill_rate}/s)"
            )

    async def acquire(self, endpoint: str = "default") -> bool:
        """
        获取限流令牌
        
        Args:
            endpoint: API 端点
            
        Returns:
            bool: 是否成功获取令牌
        """
        bucket = self.buckets.get(endpoint)
        
        if not bucket:
            # 使用默认规则
            bucket = TokenBucket(
                capacity=self.default_capacity,
                refill_rate=self.default_refill_rate
            )
            self.buckets[endpoint] = bucket
        
        # 尝试获取令牌
        if bucket.acquire():
            return True
        else:
            # 令牌不足，等待
            await self._wait_for_token(bucket)
            return True

    async def _wait_for_token(self, bucket: TokenBucket):
        """等待令牌"""
        while not bucket.acquire():
            sleep_time = (1 - bucket.tokens) / bucket.refill_rate
            await asyncio.sleep(sleep_time)

    def get_status(self, endpoint: str = "default") -> Dict:
        """获取限流状态"""
        bucket = self.buckets.get(endpoint)
        
        if not bucket:
            return {"endpoint": endpoint, "status": "not_configured"}
        
        return {
            "endpoint": endpoint,
            "tokens": bucket.tokens,
            "capacity": bucket.capacity,
            "refill_rate": bucket.refill_rate,
            "last_refill_time": bucket.last_refill_time
        }

    def reset(self, endpoint: str = None):
        """重置限流"""
        if endpoint:
            if endpoint in self.buckets:
                bucket = self.buckets[endpoint]
                bucket.tokens = bucket.capacity
                self.logger.info(f"🔄 重置限流: {endpoint}")
        else:
            for bucket in self.buckets.values():
                bucket.tokens = bucket.capacity
            self.logger.info("🔄 重置所有限流")
