"""
Test Suite: Comprehensive Cross-Automation Routing & Account Isolation Tests.
Verifies Tests 1-7 fail-closed isolation guards for Harry Potter automation.
"""
import pytest
from unittest.mock import MagicMock, patch
from config.settings import (
    AUTOMATION_ID,
    EXPECTED_GOOGLE_ACCOUNT,
    EXPECTED_DRIVE_ROOT_ID,
    EXPECTED_YOUTUBE_CHANNEL_ID,
)
from engines.drive_engine import (
    DriveVaultEngine,
    validate_hp_content_identity,
    is_valid_ready_short,
)
from engines.upload_engine import UploadEngine

def test_01_hp_content_identity_passes():
    """Test 1: Valid HP content passes identity and content type validation."""
    valid_name = "hps_ns_b1c01_gc0001_0003.mp4"
    valid_props = {
        "automation_id": "harry_potter",
        "topic": "The Boy Who Lived - Dursleys and the Strange Cat",
        "category": "novel_story",
    }
    is_valid, msg = validate_hp_content_identity(
        filename=valid_name,
        metadata_properties=valid_props,
        title="The Boy Who Lived",
        description="Harry Potter chapter story"
    )
    assert is_valid is True, f"Expected valid HP content to pass: {msg}"
    assert "Validated Harry Potter Content Identity" in msg

def test_02_foreign_al_amr_content_rejected():
    """Test 2: Foreign AL AMR content and filenames are rejected immediately."""
    # AL AMR short_man filename
    al_amr_name = "short_man_55902caa5990.mp4"
    al_amr_props = {
        "automation_id": "al_amr",
        "topic": "10 Strangest Medical Cases of 2019",
    }
    is_valid, msg = validate_hp_content_identity(
        filename=al_amr_name,
        metadata_properties=al_amr_props,
        title="10 Strangest Medical Cases of 2019"
    )
    assert is_valid is False
    assert "Automation ID mismatch" in msg or "Forbidden AL AMR content marker detected" in msg

    # Forbidden science / NASA keywords rejected even if someone sets automation_id='harry_potter'
    forbidden_props = {
        "automation_id": "harry_potter",
        "topic": "NASA-backed scientists turn plastic waste into edible cookies",
    }
    is_valid_2, msg_2 = validate_hp_content_identity(
        filename="hps_disc_science_fail.mp4",
        metadata_properties=forbidden_props,
        title="NASA-backed scientists turn plastic waste into edible cookies"
    )
    assert is_valid_2 is False
    assert "Forbidden AL AMR content marker detected" in msg_2

def test_03_missing_identity_metadata_rejected():
    """Test 3: Missing identity metadata and non-HP filenames are rejected."""
    ambiguous_name = "generic_video_clip.mp4"
    empty_props = {}
    is_valid, msg = validate_hp_content_identity(filename=ambiguous_name, metadata_properties=empty_props)
    assert is_valid is False
    assert "Missing required 'automation_id' metadata property" in msg

def test_04_wrong_google_account_fails_closed():
    """Test 4: Fail-closed hard guard stops execution if Google account does not match HP."""
    engine = DriveVaultEngine(offline_mode=False)
    
    mock_service = MagicMock()
    # Simulate returning foreign AL AMR account
    mock_service.about().get().execute.return_value = {
        "user": {"emailAddress": "jishanh776600@gmail.com"}
    }
    
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file"):
        with patch("googleapiclient.discovery.build", return_value=mock_service):
            with pytest.raises(PermissionError) as exc_info:
                engine.get_drive_service()
            assert "[HARD_ACCOUNT_GUARD_VIOLATION]" in str(exc_info.value)
            assert "jishanh776600@gmail.com" in str(exc_info.value)

def test_05_wrong_drive_root_fails_closed():
    """Test 5: Fail-closed hard guard stops execution if Drive root ID does not match HP."""
    engine = DriveVaultEngine(offline_mode=False)
    
    mock_service = MagicMock()
    mock_service.about().get().execute.return_value = {
        "user": {"emailAddress": EXPECTED_GOOGLE_ACCOUNT}
    }
    # Mock files().get returning foreign root ID
    mock_service.files().get().execute.return_value = {
        "id": "1MCyT07bauHEeBP3er17-sMxtKvMx9Puw",  # AL AMR root
        "name": "YouTube_Shorts_Vault",
    }
    
    engine._drive_service = mock_service
    with pytest.raises(PermissionError) as exc_info:
        engine.inspect_or_init_vault(create_if_missing=False)
    assert "[HARD_ROOT_GUARD_VIOLATION]" in str(exc_info.value)
    assert "1MCyT07bauHEeBP3er17-sMxtKvMx9Puw" in str(exc_info.value)

def test_06_wrong_youtube_channel_fails_closed():
    """Test 6: Fail-closed hard guard stops execution if YouTube channel does not match HP."""
    uploader = UploadEngine()
    
    mock_youtube = MagicMock()
    # Simulate foreign channel ID
    mock_youtube.channels().list().execute.return_value = {
        "items": [
            {
                "id": "UC_FOREIGN_CHANNEL_12345",
                "snippet": {"title": "Foreign Channel"},
            }
        ]
    }
    
    with pytest.raises(PermissionError) as exc_info:
        uploader.verify_channel_authorization(youtube=mock_youtube)
    assert "[HARD_CHANNEL_GUARD_VIOLATION]" in str(exc_info.value)
    assert "UC_FOREIGN_CHANNEL_12345" in str(exc_info.value)

def test_07_drive_vault_move_barrier():
    """Test 7: Vault move barrier blocks moving foreign short_man_ artifacts to production folders."""
    engine = DriveVaultEngine(offline_mode=False)
    mock_service = MagicMock()
    engine._drive_service = mock_service
    
    # Attempt to move a short_man_ file into 01_READY must fail closed with PermissionError
    with pytest.raises(PermissionError) as exc_info:
        engine.move_file_in_vault(
            file_id="1YEruY0LgQPWhKRXXk7n8KGYEA7KClW9K",
            from_folder="04_FAILED",
            to_folder="01_READY",
            filename="short_man_55902caa5990.mp4",
        )
    assert "[CROSS_AUTOMATION_BARRIER]" in str(exc_info.value)
    assert "short_man_55902caa5990.mp4" in str(exc_info.value)
