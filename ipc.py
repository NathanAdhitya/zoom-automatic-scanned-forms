import redis

r = redis.Redis(host='localhost', port=6379)


def send(text):
    r.publish("zoom", text)
