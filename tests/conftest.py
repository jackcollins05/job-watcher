"""Offline suite: accidental live requests (including DNS) are forbidden."""

import socket
import subprocess

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("live networking is forbidden in offline tests")
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    # curl runs outside Python's socket guard; tests must mock its runner too.
    monkeypatch.setattr(subprocess, "run", blocked)
