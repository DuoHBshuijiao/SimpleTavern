"""Shared shutdown intent for scheduled writers. The desktop host can cancel it."""
from threading import Event

draining = Event()
