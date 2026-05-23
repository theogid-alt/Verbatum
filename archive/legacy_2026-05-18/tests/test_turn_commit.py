from verbatim.pipeline.pipecat_processors import (
    classify_alicia_conversation_mode,
    detect_alicia_form_pattern,
    guard_alicia_response_text,
    looks_like_fragment_utterance,
    looks_like_complete_utterance,
)


def test_complete_utterance_allows_fast_commit():
    assert looks_like_complete_utterance("My budget is really big.")
    assert looks_like_complete_utterance("Hello?")
    assert looks_like_complete_utterance("thank you")


def test_incomplete_utterance_waits_for_turn_analyzer():
    assert not looks_like_complete_utterance("I was wondering if you")
    assert not looks_like_complete_utterance("like, we will not")
    assert not looks_like_complete_utterance("I am looking for a")


def test_fragment_utterance_gets_a_small_hold():
    assert looks_like_fragment_utterance("I am looking to rent, like I said,")
    assert looks_like_fragment_utterance("I want to")
    assert looks_like_fragment_utterance("well")
    assert not looks_like_fragment_utterance("I have two people talking.")
    assert not looks_like_fragment_utterance("My budget is 300k.")


def test_style_guard_removes_recaps_and_dubai_form_language():
    assert (
        guard_alicia_response_text(
            "Oh, you're looking to rent in Dubai. What's your budget for the property in Dubai?"
        )
        == "We can keep the budget flexible."
    )
    assert (
        guard_alicia_response_text(
            "That's a great budget. You can work with a lot of different properties in Dubai. What areas were you looking at?"
        )
        == "We can keep the area broad for now."
    )
    assert (
        guard_alicia_response_text(
            "That's a great income. Are you looking to rent or buy a property in Dubai?"
        )
        == "We can figure rent or purchase later."
    )
    assert (
        guard_alicia_response_text(
            "Luxury properties in Dubai can be stunning. Are you looking for a villa or an apartment?"
        )
        == "I can send both villas and apartments."
    )
    assert (
        guard_alicia_response_text("What type of property are you interested in?")
        == "I can send a few directions on WhatsApp."
    )
    assert (
        guard_alicia_response_text("What kind of property are you interested in?")
        == "I can send a few directions on WhatsApp."
    )
    assert (
        guard_alicia_response_text("Would you like to save your contact info for future inquiries?")
        == "I'll follow up on WhatsApp."
    )


def test_style_guard_keeps_direct_human_responses():
    assert guard_alicia_response_text("Yeah, sure. Which listing was it?") == (
        "Yeah, sure. Which listing was it?"
    )
    assert guard_alicia_response_text(" Worries.") == " Worries."


def test_conversation_mode_classifier_keeps_social_and_property_apart():
    assert classify_alicia_conversation_mode("Can you hear me?") == "social"
    assert classify_alicia_conversation_mode("What can you help me with?") == (
        "capability_explanation"
    )
    assert classify_alicia_conversation_mode("Can we book a viewing?") == "appointment_booking"
    assert classify_alicia_conversation_mode("Connect me to a human please") == "human_handoff"
    assert classify_alicia_conversation_mode("Repeat that") == "repeat"
    assert classify_alicia_conversation_mode("Stop asking questions") == "stop_or_correction"
    assert classify_alicia_conversation_mode("Bye") == "goodbye"
    assert classify_alicia_conversation_mode("I saw a villa on Bayut") == "property_interest"


def test_form_pattern_detection_flags_banned_sales_bot_language():
    assert detect_alicia_form_pattern("That's a great budget. What areas were you looking at?")
    assert detect_alicia_form_pattern("Are you looking to rent or buy in Dubai?")
    assert not detect_alicia_form_pattern("Yeah, I can send options on WhatsApp.")
