"""Unit tests for api_client retry behaviour (no network)."""

import unittest
from unittest import mock

import requests

import api_client
from api_client import (
    APIError,
    APIRetryExhaustedError,
    APITimeoutError,
    fetch_weather_data,
    parse_retry_after,
)


def response(status: int, json_body=None, headers=None) -> mock.Mock:
    r = mock.Mock(spec=requests.Response)
    r.status_code = status
    r.headers = headers or {}
    r.text = "body"
    r.json.return_value = json_body
    return r


@mock.patch.object(api_client.time, "sleep")
class TestFetchWeatherData(unittest.TestCase):
    def test_success(self, sleep):
        with mock.patch.object(api_client.requests, "get", return_value=response(200, {"ok": 1})) as get:
            self.assertEqual(fetch_weather_data(1), {"ok": 1})
        get.assert_called_once()
        sleep.assert_not_called()

    def test_4xx_not_retried(self, sleep):
        """HTTPError is a RequestException; it used to be swallowed and retried."""
        with mock.patch.object(api_client.requests, "get", return_value=response(404)) as get:
            with self.assertRaisesRegex(APIError, "HTTP 404"):
                fetch_weather_data(1)
        get.assert_called_once()
        sleep.assert_not_called()

    def test_5xx_retried_then_exhausted(self, sleep):
        with mock.patch.object(api_client.requests, "get", return_value=response(503)) as get:
            with self.assertRaises(APIRetryExhaustedError):
                fetch_weather_data(1, max_retries=3)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)  # no pointless sleep after the last attempt

    def test_connection_error_retried(self, sleep):
        side = [requests.ConnectionError("boom"), response(200, {"ok": 2})]
        with mock.patch.object(api_client.requests, "get", side_effect=side) as get:
            self.assertEqual(fetch_weather_data(1), {"ok": 2})
        self.assertEqual(get.call_count, 2)

    def test_retry_after_is_capped(self, sleep):
        side = [response(429, headers={"Retry-After": "86400"}), response(200, {"ok": 3})]
        with mock.patch.object(api_client.requests, "get", side_effect=side):
            self.assertEqual(fetch_weather_data(1, hard_timeout=10_000), {"ok": 3})
        sleep.assert_called_once_with(api_client.MAX_RETRY_AFTER_SECONDS)

    def test_retry_after_beyond_hard_timeout_fails_fast(self, sleep):
        with mock.patch.object(api_client.requests, "get",
                               return_value=response(429, headers={"Retry-After": "60"})):
            with self.assertRaises(APITimeoutError):
                fetch_weather_data(1, hard_timeout=30)
        sleep.assert_not_called()


class TestParseRetryAfter(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(parse_retry_after("5"), 5.0)
        self.assertEqual(parse_retry_after(" 7 "), 7.0)

    def test_http_date_in_past_is_zero(self):
        self.assertEqual(parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT"), 0.0)

    def test_garbage(self):
        self.assertIsNone(parse_retry_after(None))
        self.assertIsNone(parse_retry_after(""))
        self.assertIsNone(parse_retry_after("soon"))


if __name__ == "__main__":
    unittest.main()
