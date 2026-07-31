import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import pytest

from scripts.queue_reader import build_ssh_command, parse_queue_payload, read_remote_queue


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


class TestBuildSshCommand(unittest.TestCase):
    def test_uses_env_configuration(self):
        env = {"VPS_USER": "root", "VPS_HOST": "1.2.3.4",
               "VPS_BOT_PATH": "/root/bot", "SSH_KEY": "/k/id"}
        cmd = build_ssh_command(env)
        self.assertEqual(cmd, ["ssh", "-i", "/k/id", "root@1.2.3.4",
                               "cat /root/bot/suggestions.json 2>/dev/null || true"])

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

    def test_ssh_failure_exits_without_partial_work(self):
        env = {"VPS_USER": "root", "VPS_HOST": "h", "VPS_BOT_PATH": "/p", "SSH_KEY": "/k"}
        err = subprocess.CalledProcessError(255, "ssh", stderr="Connection refused")
        with patch("scripts.queue_reader.load_env", return_value=env), \
             patch("scripts.queue_reader.subprocess.run", side_effect=err):
            with pytest.raises(SystemExit):
                read_remote_queue()


if __name__ == "__main__":
    unittest.main()
