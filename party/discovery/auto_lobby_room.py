#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stable automatic Party Mode room selection.

The room is derived from the premade lobby members, then frozen across queue,
ready-check, champion select, and the game. Random matchmade teammates are
never used to change the room.

Only Rose users define the room: once two (or more) Rose users are discovered
sharing a premade lobby, the room is re-derived from just those Rose members
and locked in. Non-Rose lobby members never change the room, so Rose users stay
connected even as non-Rose friends join or leave the premade.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple


AUTO_ROOM_NAMESPACE = "rose-private-auto-party-v1"

DISCOVERY_PHASES = {"Lobby", "Matchmaking", "ReadyCheck"}
HOLD_PHASES = {
    "Matchmaking",
    "ReadyCheck",
    "ChampSelect",
    "GameStart",
    "Reconnect",
    "InProgress",
}
RESET_PHASES = {
    "PreEndOfGame",
    "EndOfGame",
    "WaitingForStats",
    "TerminatedInError",
}


def normalize_lobby_members(
    summoner_ids: Iterable[int],
    my_summoner_id: int,
) -> Tuple[int, ...]:
    """Normalize the raw premade lobby member list (any Rose/non-Rose mix)."""
    members = {
        int(value)
        for value in summoner_ids
        if int(value) > 0
    }
    if int(my_summoner_id) not in members or len(members) < 2:
        return ()
    return tuple(sorted(members))


def normalize_rose_members(
    rose_summoner_ids: Iterable[int],
    my_summoner_id: int,
) -> Tuple[int, ...]:
    """Normalize the set of known Rose users who are also in our lobby.

    These are the lobby members that have proven they run Rose by joining a
    Rose relay room. They are the only members that should pin the room down.
    """
    members = {
        int(value)
        for value in rose_summoner_ids
        if int(value) > 0
    }
    if int(my_summoner_id) not in members or len(members) < 2:
        return ()
    return tuple(sorted(members))


def compute_auto_room_key(members: Iterable[int]) -> str:
    normalized = tuple(sorted({int(value) for value in members}))
    payload = (
        AUTO_ROOM_NAMESPACE
        + ":"
        + ",".join(str(value) for value in normalized)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class AutoLobbyRoom:
    """State machine that prevents room churn during game transitions."""

    active_room_key: Optional[str] = None
    lobby_members: Tuple[int, ...] = field(default_factory=tuple)
    refined: bool = False

    def restore(
        self,
        room_key: Optional[str],
        lobby_members: Iterable[int],
    ) -> None:
        members = tuple(sorted({int(value) for value in lobby_members}))
        if room_key and len(members) >= 2:
            self.active_room_key = str(room_key)
            self.lobby_members = members
            # A persisted auto room came from a previous discovery pass, so it
            # is already pinned and should be treated as refined.
            self.refined = True

    def update(
        self,
        phase: str,
        premade_lobby_ids: Iterable[int],
        my_summoner_id: int,
        rose_lobby_ids: Iterable[int] = (),
    ) -> Optional[str]:
        phase = str(phase or "")
        full_members = normalize_lobby_members(
            premade_lobby_ids,
            my_summoner_id,
        )
        rose_members = normalize_rose_members(
            rose_lobby_ids,
            my_summoner_id,
        )

        # Once matchmaking starts, never derive from champion-select myTeam:
        # that list contains matchmade strangers and can change visibility.
        if phase in HOLD_PHASES:
            return self.active_room_key

        if phase in RESET_PHASES:
            self.clear()
            return None

        # Discovery: Rose-only room takes priority over the raw lobby. As soon
        # as 2+ Rose users share the premade, we pin the room to them so that
        # non-Rose friends joining/leaving can no longer change it.
        if rose_members:
            room_key = compute_auto_room_key(rose_members)
            self.active_room_key = room_key
            self.lobby_members = rose_members
            self.refined = True
            return room_key

        # Once refined, stay pinned to the Rose room even if a transient state
        # leaves us briefly without a second Rose member in view.
        if self.refined:
            return self.active_room_key

        # Not enough Rose users discovered yet: bootstrap from the full premade
        # lobby so that all Rose clients in the lobby find each other, then the
        # first branch above refines the room to Rose-only members.
        if full_members:
            room_key = compute_auto_room_key(full_members)
            self.active_room_key = room_key
            self.lobby_members = full_members
            return room_key

        # In the plain lobby, a one-person lobby means the premade disbanded.
        if phase in DISCOVERY_PHASES and not full_members:
            self.clear()
            return None

        return self.active_room_key

    def clear(self) -> None:
        self.active_room_key = None
        self.lobby_members = ()
        self.refined = False
