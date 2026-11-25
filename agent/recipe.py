"""The test recipe, written as a "chef's script".

In the real product this is produced by the recipe-prep AI pass. For the
technical test we hand-write one recipe so we can focus on the live call.
"""

RECIPE = {
    "title": "Garlic Tomato Pasta",
    "serves": 2,
    "equipment": ["large pot", "large frying pan", "cutting board", "chef's knife", "colander", "wooden spoon"],
    "ingredients": [
        "200 g spaghetti",
        "1 small onion",
        "3 cloves garlic",
        "1 can (400 g) chopped tomatoes",
        "3 tbsp olive oil",
        "1 tsp salt (plus a big pinch for the pasta water)",
        "a pinch of chili flakes (optional)",
        "a few basil leaves (optional)",
        "parmesan to serve (optional)",
    ],
    "steps": [
        {
            "title": "Boil the water",
            "do": "Fill the large pot about 3/4 with water, add a big pinch of salt, lid on, high heat.",
            "check": "None needed — just confirm it's on the stove.",
            "mistakes": ["Not enough salt in the water — it should taste a little like the sea."],
        },
        {
            "title": "Chop onion and garlic",
            "do": "Peel and finely dice the onion. Peel and thinly slice the garlic.",
            "check": "Ask to SEE the cutting board. Onion pieces should be small, roughly pea-sized and even. Garlic slices thin.",
            "mistakes": [
                "Fingers flat instead of curled into a 'claw' while cutting.",
                "Uneven onion pieces — big chunks stay crunchy.",
            ],
        },
        {
            "title": "Soften the onion",
            "do": "Frying pan on MEDIUM heat, add 3 tbsp olive oil, then the onion and the 1 tsp salt. Stir now and then for about 6 minutes.",
            "stove_moment": "Ask them to point the camera at the pan. Onion should be soft and see-through, only lightly golden at the edges — NOT browned.",
            "timer": {"label": "Onion", "minutes": 6},
            "mistakes": ["Heat too high — onion browns and burns before it softens."],
        },
        {
            "title": "Add garlic and chili",
            "do": "Add the garlic (and chili flakes if using). Stir for about 1 minute until it smells fragrant.",
            "stove_moment": "Look at the pan: garlic should be pale gold at most. If it's turning brown, take the pan off the heat right away.",
            "mistakes": ["Burnt garlic tastes bitter — it goes from good to burnt in seconds."],
        },
        {
            "title": "Simmer the sauce",
            "do": "Pour in the tomatoes, stir, turn heat to LOW-MEDIUM so it gently bubbles. Simmer about 10 minutes, stirring now and then.",
            "stove_moment": "Check the bubbling: small lazy bubbles, not a violent splattering boil.",
            "timer": {"label": "Sauce", "minutes": 10},
            "mistakes": ["Boiling too hard — sauce splatters and catches on the bottom."],
        },
        {
            "title": "Cook the pasta",
            "do": "Once the water is at a rolling boil, add the spaghetti, stir in the first minute so it doesn't stick. Cook for the time on the packet minus 1 minute (usually about 9 minutes).",
            "timer": {"label": "Pasta", "minutes": 9},
            "mistakes": ["Not stirring at the start — spaghetti clumps together."],
        },
        {
            "title": "Save water, drain, combine",
            "do": "Before draining, scoop out about half a mug of pasta water. Drain the pasta, put it into the sauce pan, add a splash of the pasta water and toss for 1 minute on low heat.",
            "check": "Ask to SEE the pan. The sauce should cling to the pasta and look glossy, not watery or dry. Add more pasta water if dry.",
            "mistakes": ["Pouring all the pasta water away — it's what makes the sauce silky."],
        },
        {
            "title": "Taste and serve",
            "do": "Taste and add salt if needed. Plate it, tear over basil, add parmesan if you like.",
            "check": "Ask to see the finished plate. Give genuine praise plus one or two specific tips for next time.",
            "mistakes": [],
        },
    ],
}


def recipe_as_script() -> str:
    """Turn the recipe into plain text for the chef's instructions."""
    r = RECIPE
    lines = [f"RECIPE: {r['title']} (serves {r['serves']})", ""]
    lines.append("EQUIPMENT: " + ", ".join(r["equipment"]))
    lines.append("")
    lines.append("INGREDIENTS:")
    lines += [f"- {i}" for i in r["ingredients"]]
    lines.append("")
    lines.append("STEPS (step 0 = gathering ingredients, then these):")
    for n, s in enumerate(r["steps"], start=1):
        lines.append(f"Step {n}: {s['title']}")
        lines.append(f"  Do: {s['do']}")
        if s.get("check"):
            lines.append(f"  Check-in: {s['check']}")
        if s.get("stove_moment"):
            lines.append(f"  Stove moment: {s['stove_moment']}")
        if s.get("timer"):
            t = s["timer"]
            lines.append(f"  Timer: start a '{t['label']}' timer for {t['minutes']} minutes when they begin this.")
        if s["mistakes"]:
            lines.append("  Common mistakes: " + " | ".join(s["mistakes"]))
    return "\n".join(lines)
