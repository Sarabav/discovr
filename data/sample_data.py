"""Hardcoded sample data for the Discovr proof of concept.

A single fictional business (a local dental clinic) stands in for real
scraped data, so the app always has a complete analysis to display.
"""

BUSINESS_PROFILE = {
    "name": "Bright Smile Dental Clinic",
    "website": "https://brightsmiledental.example.com",
    "facebook": "@BrightSmileDentalClinic",
    "instagram": "@brightsmile.dental",
}

CATEGORY_FINDINGS = {
    "consistency": {
        "label": "Consistency",
        "score": 62,
        "findings": [
            "Business name appears as 'Bright Smile Dental' on Facebook but 'Bright Smile Dental Clinic' on the website.",
            "Phone number on the Instagram bio does not match the website's listed number.",
            "Business hours are listed on the website but missing from both social profiles.",
        ],
    },
    "structured_data": {
        "label": "Structured Data",
        "score": 40,
        "findings": [
            "No LocalBusiness schema markup detected on the website.",
            "Missing Organization schema for logo and social profile links.",
            "No FAQ schema present despite an FAQ section on the site.",
        ],
    },
    "content_clarity": {
        "label": "Content Clarity",
        "score": 75,
        "findings": [
            "Homepage clearly states services offered (general, cosmetic, and pediatric dentistry).",
            "Service pages lack concise summaries near the top, requiring AI crawlers to parse long paragraphs.",
            "No dedicated page answering common patient questions in plain language.",
        ],
    },
    "social_presence": {
        "label": "Social Presence",
        "score": 55,
        "findings": [
            "Facebook page is active with recent posts, but Instagram has not posted in over two months.",
            "Neither social profile links back to the website in a prominent way.",
            "No consistent branding (logo/colors) between the Facebook and Instagram profile images.",
        ],
    },
}

RECOMMENDATIONS = [
    {
        "priority": "High",
        "category": "structured_data",
        "text": "Add LocalBusiness schema markup to the website to help AI assistants correctly identify business details.",
    },
    {
        "priority": "High",
        "category": "consistency",
        "text": "Standardize the business name and phone number across the website, Facebook, and Instagram.",
    },
    {
        "priority": "Medium",
        "category": "social_presence",
        "text": "Resume regular Instagram posting to signal an active, trustworthy business presence.",
    },
    {
        "priority": "Medium",
        "category": "content_clarity",
        "text": "Add short, plain-language summaries at the top of each service page for easier AI comprehension.",
    },
    {
        "priority": "Low",
        "category": "structured_data",
        "text": "Implement FAQ schema on the existing FAQ section to improve visibility in AI-generated answers.",
    },
]
