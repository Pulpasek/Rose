#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Randomization Handler
Handles random skin selection logic (supports all-skins and favorites-only modes)
"""

import random
from typing import Optional, Tuple
from state import SharedState
from utils.core.logging import get_logger
from utils.core.utilities import is_base_skin
from utils.core.favorites import (
    get_favorite_skins_for_champion,
    get_favorite_chromas_for_skin,
)

log = get_logger()


class RandomizationHandler:
    """Handles random skin selection logic"""
    
    def __init__(self, state: SharedState, skin_scraper=None):
        """Initialize randomization handler
        
        Args:
            state: Shared application state
            skin_scraper: Skin scraper instance
        """
        self.state = state
        self.skin_scraper = skin_scraper
        self._randomization_in_progress = False
        self._randomization_started = False
    
    def handle_dice_click_disabled(self, current_skin_id: Optional[int], mode: str = "all") -> bool:
        """Handle dice button click in disabled state - start randomization
        
        Args:
            current_skin_id: Current skin ID from UI
            mode: "all" for all skins, "favorites" for favorites only
            
        Returns:
            True if randomization was started, False otherwise
        """
        # Prevent multiple simultaneous randomization attempts
        if self._randomization_started:
            log.debug("[UI] Randomization already in progress, ignoring click")
            return False
        
        log.info(f"[UI] Starting random skin selection (mode={mode})")
        self._randomization_started = True
        
        # Force champion's base skin first
        champion_id = self.skin_scraper.cache.champion_id if self.skin_scraper and self.skin_scraper.cache else None
        base_champion_skin_id = champion_id * 1000 if champion_id else None
        
        if current_skin_id == base_champion_skin_id:
            # Already champion's base skin, proceed with randomization
            self._start_randomization(mode=mode)
            return True
        else:
            # Need to force champion's base skin first
            return False  # Caller should call force_base_skin_and_randomize
    
    def handle_dice_click_enabled(self):
        """Handle dice button click in enabled state - cancel randomization"""
        log.info("[UI] Cancelling random skin selection")
        self.cancel()
    
    def force_base_skin_and_randomize(self, lcu, mode: str = "all") -> bool:
        """Force champion's base skin via LCU API then start randomization
        
        Args:
            lcu: LCU instance
            mode: "all" or "favorites"
            
        Returns:
            True if base skin was forced and randomization started, False otherwise
        """
        if not self.state.locked_champ_id:
            log.warning("[UI] Cannot force base skin - no locked champion")
            return False
        
        # Set flag to prevent cancellation during randomization BEFORE the
        # temporary base-skin force. If the UI detects the base skin transition
        # before the random roll is activated, it cancels the mode and leaves the
        # champion stuck on the default skin.
        self._randomization_in_progress = True
        self.state.random_mode_active = True
        self.state.random_mode_type = mode
        self.state.random_skin_name = None
        self.state.random_skin_id = None
        self.state.random_chroma_id = None
        
        # Get champion's base skin ID (champion_id * 1000)
        champion_id = self.state.locked_champ_id
        base_skin_id = champion_id * 1000
        log.info(f"[UI] Forcing champion base skin: {base_skin_id} (champion {champion_id})")
        
        # Force base skin via LCU
        try:
            if not lcu:
                log.warning("[UI] No LCU instance available")
                self.state.random_mode_active = False
                self.state.random_mode_type = "all"
                self._randomization_in_progress = False
                return False
            
            # Try to set base skin
            if lcu.set_my_selection_skin(base_skin_id):
                log.info(f"[UI] Forced champion base skin: {base_skin_id}")
                # Start randomization immediately
                self._start_randomization(mode=mode)
                return True
            else:
                log.warning("[UI] Failed to force champion base skin")
                self.state.random_mode_active = False
                self.state.random_mode_type = "all"
                self._randomization_in_progress = False
                self._randomization_started = False
                return False
        except Exception as e:
            log.error(f"[UI] Error forcing champion base skin: {e}")
            self.state.random_mode_active = False
            self.state.random_mode_type = "all"
            self._randomization_in_progress = False
            self._randomization_started = False
            return False
    
    def _start_randomization(self, mode: str = "all"):
        """Start the randomization sequence"""
        # Check if randomization was cancelled
        if not self._randomization_started:
            log.debug("[UI] Randomization was cancelled, aborting start")
            self._randomization_in_progress = False
            return
        
        try:
            # Disable HistoricMode if active
            try:
                if getattr(self.state, 'historic_mode_active', False):
                    self.state.historic_mode_active = False
                    self.state.historic_skin_id = None
                    log.info("[HISTORIC] Historic mode DISABLED due to RandomMode activation")
                    # Broadcast state to JavaScript
                    try:
                        if self.state and hasattr(self.state, 'ui_skin_thread') and self.state.ui_skin_thread:
                            self.state.ui_skin_thread._broadcast_historic_state()
                    except Exception as e:
                        log.debug(f"[UI] Failed to broadcast historic state on RandomMode activation: {e}")
            except Exception:
                pass
            
            # Select random skin
            random_selection = self.select_random_skin(mode=mode)
            if random_selection:
                random_skin_name, random_skin_id, selected_chroma_id = random_selection
                self.state.random_skin_name = random_skin_name
                self.state.random_skin_id = random_skin_id
                self.state.random_chroma_id = selected_chroma_id
                self.state.random_mode_active = True
                self.state.random_mode_type = mode
                log.info(f"[UI] Random skin selected: {random_skin_name} (ID: {random_skin_id}, Chroma: {selected_chroma_id}, Mode: {mode})")

                # Apply the random choice to the LCU skin selection immediately so
                # the lobby preview and picked skin actually change instead of
                # staying on the champion's default skin.
                lcu = getattr(self.skin_scraper, 'lcu', None) if self.skin_scraper else None
                if lcu and random_skin_id is not None:
                    try:
                        if lcu.set_my_selection_skin(random_skin_id):
                            log.info(f"[UI] Applied random skin to LCU selection: {random_skin_id}")
                        else:
                            log.warning(f"[UI] Failed to apply random skin to LCU selection: {random_skin_id}")
                    except Exception as e:
                        log.warning(f"[UI] Exception while applying random skin to LCU selection: {e}")
                
                # Broadcast random mode state to JavaScript
                try:
                    if self.state and hasattr(self.state, 'ui_skin_thread') and self.state.ui_skin_thread:
                        self.state.ui_skin_thread._broadcast_random_mode_state()
                except Exception as e:
                    log.debug(f"[UI] Failed to broadcast random mode state: {e}")
            else:
                log.warning(f"[UI] No random skin available for mode={mode}")
                self.cancel()
        except Exception as e:
            log.error(f"[UI] Unexpected error in _start_randomization: {e}")
            self.cancel()
        finally:
            # Clear the randomization flags AFTER everything is set up
            self._randomization_in_progress = False
            self._randomization_started = False
    
    def cancel(self):
        """Cancel randomization and reset state"""
        # Reset state
        self.state.random_skin_name = None
        self.state.random_skin_id = None
        self.state.random_chroma_id = None
        self.state.random_mode_active = False
        self.state.random_mode_type = "all"
        
        # Broadcast random mode state to JavaScript
        try:
            if self.state and hasattr(self.state, 'ui_skin_thread') and self.state.ui_skin_thread:
                self.state.ui_skin_thread._broadcast_random_mode_state()
        except Exception as e:
            log.debug(f"[UI] Failed to broadcast random mode state on cancel: {e}")
        
        # Clear randomization flags
        self._randomization_in_progress = False
        self._randomization_started = False
    
    def select_random_skin(self, mode: str = "all") -> Optional[Tuple[str, int, int]]:
        """Select a random skin and chroma from available skins
        
        Args:
            mode: "all" to roll from all skins, "favorites" to roll strictly from favorites
            
        Returns:
            Tuple of (skin_name, skin_id, chroma_id) or None if no skin is available
        """
        if not self.skin_scraper or not self.skin_scraper.cache.skins:
            log.warning("[UI] No skins available for random selection")
            return None
        
        # Filter out the champion's base skin and actual chromas
        champion_id = self.skin_scraper.cache.champion_id
        base_champion_skin_id = champion_id * 1000 if champion_id else None
        
        chroma_id_map = self.skin_scraper.cache.chroma_id_map if self.skin_scraper and self.skin_scraper.cache else None
        available_skins = [
            skin for skin in self.skin_scraper.cache.skins 
            if skin.get('skinId') != base_champion_skin_id and is_base_skin(skin.get('skinId'), chroma_id_map)
        ]
        
        # If favorites mode, filter down to favorited skins only
        if mode == "favorites" and champion_id:
            fav_skin_ids = get_favorite_skins_for_champion(champion_id)
            if not fav_skin_ids:
                log.warning(f"[UI] No favorite skins defined for champion {champion_id}")
                return None
            
            fav_available = [skin for skin in available_skins if skin.get('skinId') in fav_skin_ids]
            if not fav_available:
                log.warning(f"[UI] None of the favorited skins {fav_skin_ids} matched available skins")
                return None
            available_skins = fav_available
            log.info(f"[UI] Filtered to {len(available_skins)} favorite skins for champion {champion_id}")
        
        # Debug logging
        log.debug(f"[UI] Champion ID: {champion_id}, Base skin ID: {base_champion_skin_id}")
        log.debug(f"[UI] Total skins in cache: {len(self.skin_scraper.cache.skins)}")
        log.debug(f"[UI] Available skins for random selection: {len(available_skins)}")
        for skin in available_skins[:5]:  # Show first 5 for debugging
            log.debug(f"[UI] Available skin: {skin.get('skinName')} (ID: {skin.get('skinId')})")
        
        if not available_skins:
            log.warning("[UI] No non-base skins available for random selection")
            return None
        
        # Select random skin
        selected_skin = random.choice(available_skins)
        skin_id = selected_skin.get('skinId')
        localized_skin_name = selected_skin.get('skinName', '')
        
        if not localized_skin_name or not skin_id:
            log.warning("[UI] Selected skin has no name or ID")
            return None
        
        english_skin_name = localized_skin_name
        
        # Now select a random chroma for this skin
        available_chromas = []
        
        # Always include the base chroma (skin_id itself)
        available_chromas.append(skin_id)
        
        # Get all chromas for this skin from the scraper
        try:
            chromas_list = self.skin_scraper.get_chromas_for_skin(skin_id)
            if chromas_list:
                for chroma in chromas_list:
                    # Chromas are stored with 'id' key, not 'chromaId'
                    chroma_id = chroma.get('id') if isinstance(chroma, dict) else chroma
                    if chroma_id and chroma_id not in available_chromas:
                        available_chromas.append(chroma_id)
                log.debug(f"[UI] Found {len(chromas_list)} chromas for skin {skin_id}: {[c.get('id') for c in chromas_list]}")
            else:
                log.debug(f"[UI] No chromas returned for skin {skin_id}")
        except Exception as e:
            log.warning(f"[UI] Failed to get chromas for skin {skin_id}: {e}")
        
        # If in favorites mode, filter to favorite chromas only
        if mode == "favorites" and champion_id:
            fav_chromas = get_favorite_chromas_for_skin(champion_id, skin_id)
            if fav_chromas:
                available_chromas = [c for c in available_chromas if c in fav_chromas]
                log.info(f"[UI] Filtered to {len(available_chromas)} favorite chromas for skin {skin_id}")
        
        # If no chromas available (shouldn't happen, but just in case), use base chroma
        if not available_chromas:
            available_chromas = [skin_id]
            log.warning(f"[UI] No chromas available for skin {skin_id}, using base chroma")
        
        # Select random chroma
        selected_chroma_id = random.choice(available_chromas)
        
        log.info(f"[UI] Selected random skin '{english_skin_name}' (ID: {skin_id}) with chroma {selected_chroma_id}")
        return (english_skin_name, skin_id, selected_chroma_id)
    
    def update_dice_button(self, current_skin_id: Optional[int]):
        """Broadcast dice button state to JavaScript"""
        # Skip dice button in Swiftplay mode
        if self.state.is_swiftplay_mode:
            return
        
        # Broadcast random mode state to JavaScript
        if current_skin_id:
            try:
                if self.state and hasattr(self.state, 'ui_skin_thread') and self.state.ui_skin_thread:
                    self.state.ui_skin_thread._broadcast_random_mode_state()
            except Exception as e:
                log.debug(f"[UI] Failed to broadcast random mode state on dice button update: {e}")
    
    @property
    def randomization_in_progress(self) -> bool:
        """Check if randomization is in progress"""
        return self._randomization_in_progress
    
    @property
    def randomization_started(self) -> bool:
        """Check if randomization has started"""
        return self._randomization_started
    
    @randomization_started.setter
    def randomization_started(self, value: bool):
        """Set randomization started flag"""
        self._randomization_started = value
    
    def reset_on_skin_change(self):
        """Reset randomization flags when skin changes"""
        if self._randomization_started:
            log.debug("[UI] Resetting randomization flag due to skin change")
            self._randomization_started = False
            # Also reset in-progress flag if it was set
            if self._randomization_in_progress:
                log.debug("[UI] Cancelling randomization in progress due to skin change")
                self._randomization_in_progress = False
                # Cancel the state but don't call full cancel to avoid double broadcast
                if self.state.random_mode_active:
                    self.state.random_skin_name = None
                    self.state.random_skin_id = None
                    self.state.random_chroma_id = None
                    self.state.random_mode_active = False
                    self.state.random_mode_type = "all"
                    try:
                        if self.state and hasattr(self.state, 'ui_skin_thread') and self.state.ui_skin_thread:
                            self.state.ui_skin_thread._broadcast_random_mode_state()
                    except Exception as e:
                        log.debug(f"[UI] Failed to broadcast random mode state on skin change: {e}")
