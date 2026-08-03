import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import pytest

from scripts.queue_reader import (
    NO_QUEUE_SENTINEL, build_ssh_command, parse_queue_payload, read_remote_queue,
)


class TestParseQueuePayload(unittest.TestCase):
    def test_reads_suggestions_list(self):
        payload = json.dumps({"suggestions": ["Vauban", "Lyautey"]})
        self.assertEqual(parse_queue_payload(payload), ["Vauban", "Lyautey"])

    def test_empty_payload_is_empty_queue(self):
        self.assertEqual(parse_queue_payload(""), [])

    def test_malformed_payload_is_empty_queue(self):
        self.assertEqual(parse_queue_payload("{ pas du json"), [])

    def test_missing_key_is_empty_queue(self):
        self.assertEqual(parse_queue_payload(json.dumps({"autre": 1})), [])

    def test_filters_out_non_string_items(self):
        """suggestions.json is a plain hand-editable file on the VPS, not
        exclusively produced by /suggest. A non-string item reaching
        Utils.names_match would raise TypeError from unicodedata.normalize
        before add_figures.collect()'s try block, discarding the whole run."""
        payload = json.dumps({"suggestions": ["Vauban", 42, None, "  ", "Lyautey"]})
        self.assertEqual(parse_queue_payload(payload), ["Vauban", "Lyautey"])


class TestBuildSshCommand(unittest.TestCase):
    def test_uses_env_configuration(self):
        env = {"VPS_USER": "root", "VPS_HOST": "1.2.3.4",
               "VPS_BOT_PATH": "/root/bot", "SSH_KEY": "/k/id"}
        cmd = build_ssh_command(env)
        self.assertEqual(cmd, ["ssh", "-i", "/k/id", "root@1.2.3.4",
                               "if [ -f /root/bot/suggestions.json ]; then "
                               "cat /root/bot/suggestions.json; else "
                               f"echo {NO_QUEUE_SENTINEL}; fi"])

    def test_missing_host_raises(self):
        with pytest.raises(SystemExit):
            build_ssh_command({"VPS_USER": "root"})


class TestReadRemoteQueue(unittest.TestCase):
    def test_returns_names_from_ssh_output(self):
        result = Mock(stdout=json.dumps({"suggestions": ["Vauban"]}))
        env = {"VPS_USER": "root", "VPS_HOST": "h", "VPS_BOT_PATH": "/p", "SSH_KEY": "/k"}
        with patch("scripts.queue_reader.load_env", return_value=env), \
             patch("scripts.queue_reader.subprocess.run", return_value=result):
            self.assertEqual(read_remote_queue(), ["Vauban"])

    def test_missing_queue_file_is_empty_queue(self):
        """The sentinel means 'no queue file yet' — benign, not an error."""
        result = Mock(stdout=NO_QUEUE_SENTINEL + "\n")
        env = {"VPS_USER": "root", "VPS_HOST": "h", "VPS_BOT_PATH": "/p", "SSH_KEY": "/k"}
        with patch("scripts.queue_reader.load_env", return_value=env), \
             patch("scripts.queue_reader.subprocess.run", return_value=result):
            self.assertEqual(read_remote_queue(), [])

    def test_ssh_failure_exits_without_partial_work(self):
        env = {"VPS_USER": "root", "VPS_HOST": "h", "VPS_BOT_PATH": "/p", "SSH_KEY": "/k"}
        err = subprocess.CalledProcessError(255, "ssh", stderr="Connection refused")
        with patch("scripts.queue_reader.load_env", return_value=env), \
             patch("scripts.queue_reader.subprocess.run", side_effect=err):
            with pytest.raises(SystemExit):
                read_remote_queue()

    def test_read_failure_does_not_silently_yield_empty_queue(self):
        """A wrong VPS_BOT_PATH, permission denied, or SSH reaching the wrong
        host must surface as an error, never be indistinguishable from 'the
        queue is empty' (the bug this fix closes)."""
        env = {"VPS_USER": "root", "VPS_HOST": "h", "VPS_BOT_PATH": "/p", "SSH_KEY": "/k"}
        err = subprocess.CalledProcessError(1, "ssh", stderr="Permission denied")
        with patch("scripts.queue_reader.load_env", return_value=env), \
             patch("scripts.queue_reader.subprocess.run", side_effect=err):
            with pytest.raises(SystemExit):
                read_remote_queue()


if __name__ == "__main__":
    unittest.main()
