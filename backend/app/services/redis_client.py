import redis, json

class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host="localhost",
            port=6379,
            db=0,
            decode_responses=True
        )
    
    def set(self, key, value, ex=3600):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return self.client.set(key, value, ex=ex)
    
    def get(self, key):
        value = self.client.get(key)
        if value and isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    
    def delete(self, key):
        return self.client.delete(key)
    
    def exists(self, key):
        return self.client.exists(key)
    
    def get_or_set(self, key, value, ex=3600):
        if self.exists(key):
            return self.get(key)
        self.set(key, value, ex=ex)
        return value

redis_client = RedisClient()