# Twiver

An infinite stream connected to Twitter and focusing on Retweets forecasting for River.  

#### Installation 🤖

```sh
pip install git+https://github.com/raphaelsty/twiver --upgrade
```

#### Bearer token

To use Twiver, you must create a Twitter developer account. Everything is explained [here](https://developer.twitter.com/en/docs/authentication/oauth-2-0/bearer-tokens). Once you have your `BEARER_TOKEN`, you can save it as an environment variable.

```sh
export BEARER_TOKEN='<YOUR_BEARER_TOKEN>'
```

#### Quickstart 🐥 

```python
>>> from twiver import stream
>>> import datetime
>>> import os

>>> bearer_token = os.environ["BEARER_TOKEN"]

>>> stream = stream.Twitter(
...     bearer_token = bearer_token,
...     sample_rules = [
...         {"value": "paris lang:fr", "tag": "Paris fr"},
...         {"value": "paris lang:en", "tag": "Paris en"},
...     ],
...     delay=datetime.timedelta(seconds=20),
... )

>>> for i, x, y in stream:
...     break

>>> x
{'created_at': datetime.datetime(2021, 4, 26, 22, 59, 16), 'text': 'Going to the toilets.', 'username': 'XXXXX', 'reply': False, 'id': '1386817182877822997', 'retweet_count': 0, 'reply_count': 0, 'like_count': 0, 'quote_count': 0, 'followers_count': 292, 'following_count': 691, 'tweet_count': 2803, 'listed_count': 0}
```