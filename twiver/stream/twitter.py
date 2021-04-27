__all__ = ["Twitter"]


import bisect
import collections
import datetime as dt
import json
import typing
from copy import deepcopy

import requests


class Memento(collections.namedtuple("Memento", "key i x t_expire")):
    def __lt__(self, other):
        return self.t_expire < other.t_expire


class Twitter:
    """Generate a stream of real-time tweets for River.

    Parameters
    ----------
        bearer_token
            Token given by twitter developper app.
        sample_rule
            Set of rules to filter stream of tweets.
        moment
            The attribute used for measuring time. If a callable is passed, then it is expected
            to take as input a `dict` of features. If `None`, then the observations are implicitly
            timestamped in the order in which they arrive. If a `str` is passed, then it will be
            used to obtain the time from the input features.
        delay
            The amount of time to wait before revealing the target associated with each
            observation to the model. This value is expected to be able to sum with the `moment`
            value. For instance, if `moment` is a `datetime.date`, then `delay` is expected to be a
            `datetime.timedelta`. If a callable is passed, then it is expected to take as input a
            `dict` of features and the target. If a `str` is passed, then it will be used to access
            the relevant field from the features. If `None` is passed, then no delay will be used,
            which leads to doing standard online validation. If a scalar is passed, such an `int`
            or a `datetime.timedelta`, then the delay is constant.
        minimum_header_size
            Minimum number of tweets that are available to update the model to make an http request
            to Twitter. Small value of minimum_header_size may lead to a 429 Too Many Requests
            error.
        maximum_header_size
            Maximum number of tweets per request to the twitter API to get the ground truth.
            Twitter limit the maximum header size.
        copy
            If `True`, then a separate copy of the features are yielded the second time
            around. This ensures that inadvertent modifications in downstream code don't have any
            effect.

    Examples
    --------
    >>> from twiver import stream
    >>> import datetime
    >>> import os

    >>> bearer_token = os.environ["BEARER_TOKEN"]

    >>> stream = stream.Twitter(
    ...     bearer_token = bearer_token,
    ...     sample_rules = [
    ...         {"value": "paris lang:fr", "tag": "Tweets that mention Paris in French."},
    ...         {"value": "paris lang:en", "tag": "Tweets that mention Paris in English."},
    ...     ],
    ...     delay=datetime.timedelta(seconds=20),
    ... )

    >>> for i, x, y in stream:
    ...     break

    References
    ----------
    [^1]: [River Streaming Module](https://github.com/online-ml/river/blob/master/river/stream/qa.py)

    """

    def __init__(
        self,
        bearer_token: str,
        sample_rules: typing.List,
        delay: typing.Union[str, int, dt.timedelta, typing.Callable],
        minimum_header_size: int = 10,
        maximum_header_size: int = 100,
        copy: bool = True,
    ):
        self.sample_rules = sample_rules
        self.delay = delay
        self.copy = copy
        self.minimum_header_size = minimum_header_size
        self.maximum_header_size = maximum_header_size

        self.key = "id"
        self.moment = "created_at"

        self.headers = self.create_headers(bearer_token=bearer_token)
        self.delete_all_rules(rules=self.get_rules())
        self.set_rules()
        self.y_queue = {}

    @staticmethod
    def create_headers(bearer_token: str):
        return {"Authorization": f"Bearer {bearer_token}"}

    def get_rules(self):
        response = requests.get(
            "https://api.twitter.com/2/tweets/search/stream/rules", headers=self.headers
        )
        if response.status_code != 200:
            raise Exception(
                "Cannot get rules (HTTP {}): {}".format(response.status_code, response.text)
            )
        return response.json()

    def delete_all_rules(self, rules: typing.List):
        if rules is None or "data" not in rules:
            return None

        ids = list(map(lambda rule: rule["id"], rules["data"]))
        payload = {"delete": {"ids": ids}}
        response = requests.post(
            "https://api.twitter.com/2/tweets/search/stream/rules",
            headers=self.headers,
            json=payload,
        )
        if response.status_code != 200:
            raise Exception(
                "Cannot delete rules (HTTP {}): {}".format(response.status_code, response.text)
            )

    def set_rules(self):
        response = requests.post(
            "https://api.twitter.com/2/tweets/search/stream/rules",
            headers=self.headers,
            json={"add": self.sample_rules},
        )
        if response.status_code != 201:
            raise Exception(
                "Cannot add rules (HTTP {}): {}".format(response.status_code, response.text)
            )

    def twitter_stream(self):
        response = requests.get(
            "https://api.twitter.com/2/tweets/search/stream?tweet.fields=created_at,public_metrics,entities,in_reply_to_user_id&expansions=author_id&user.fields=public_metrics",
            headers=self.headers,
            stream=True,
        )
        if response.status_code != 200:
            raise Exception(
                "Cannot get stream (HTTP {}): {}".format(response.status_code, response.text)
            )
        for response_line in response.iter_lines():
            if response_line:
                tweet = json.loads(response_line)
                # Remove RT from incoming stream.
                if "RT @" not in tweet["data"]["text"]:
                    yield self.process(tweet)

    def targets(self, key_old: str, i_old: int, x_old: typing.Dict):
        """Retrieve tweets."""
        self.y_queue[key_old] = (i_old, x_old)

        if len(self.y_queue) >= self.minimum_header_size:

            ids = list(self.y_queue.keys())[: self.maximum_header_size]
            response = requests.get(
                f"https://api.twitter.com/2/tweets?tweet.fields=created_at,public_metrics,entities,in_reply_to_user_id&expansions=author_id&user.fields=public_metrics&ids={','.join(ids)}",
                headers=self.headers,
            )
            tweets = json.loads(response.text)
            if "data" in tweets:
                for tweet in tweets["data"]:
                    y_old = tweet["public_metrics"]["retweet_count"]
                    i_old, x_old = self.y_queue.pop(tweet["id"])
                    yield i_old, x_old, y_old

            # Drop deleted tweets from the queue.
            for id in ids:
                if id in self.y_queue:
                    self.y_queue.pop(id)

    @staticmethod
    def format_date(date: str):
        date = date.split(".")[0].replace("T", " ")
        return dt.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")

    def process(self, tweet: typing.Dict):
        x = {}
        x["created_at"] = self.format_date(tweet["data"]["created_at"])
        x["text"] = tweet["data"]["text"]
        x["username"] = tweet["includes"]["users"][0]["username"]
        x["reply"] = "in_reply_to_user_id" in tweet["data"]
        x["id"] = tweet["data"]["id"]
        x.update(tweet["data"]["public_metrics"])
        x.update(tweet["includes"]["users"][0]["public_metrics"])
        return x

    def __iter__(self):
        # Determine how to insert mementos into the queue
        if callable(self.delay) or isinstance(self.delay, str):

            def queue(q, el):
                bisect.insort(q, el)

        else:

            def queue(q, el):
                q.append(el)

        # Coerce moment to a function
        if isinstance(self.moment, str):

            def get_moment(_, x):
                return x[self.moment]

        elif callable(self.moment):

            def get_moment(_, x):
                return self.moment(x)

        else:

            def get_moment(i, _):
                return i

        # Coerce delay to a function
        if self.delay is None:

            def get_delay(i, _):
                return 0

        elif isinstance(self.delay, str):

            def get_delay(x, _):
                return x[self.delay]

        elif not callable(self.delay):

            def get_delay(_, __):
                return self.delay

        else:
            get_delay = self.delay

        def get_key(x):
            return x[self.key]

        mementos: typing.List[Memento] = []

        for i, x in enumerate(self.twitter_stream()):

            t = get_moment(i, x)
            d = get_delay(i, x)
            key = get_key(x)

            while mementos:

                # Get the oldest answer
                key_old, i_old, x_old, t_expire = mementos[0]

                # If the oldest answer isn't old enough then stop
                if t_expire > t:
                    break

                yield from self.targets(key_old, i_old, x_old)

                del mementos[0]

            queue(mementos, Memento(key, i, x, t + d))
            if self.copy:
                x = deepcopy(x)
            yield i, x, None
