"""
Fundamentals/news + session-timing context layer.

Not implemented yet. Planned responsibilities:

  context/calendar.py   Economic calendar events (e.g. high-impact news
                         windows to respect/avoid per playbook rules).
  context/news.py       Relevant headlines for the instrument in play.
  context/sessions.py   Kill-zone / session timing — London, New York,
                         Asian session windows, in the instrument's
                         relevant timezone, used to gate when the agent
                         is even allowed to consider a trade.

Output of this module is handed to agent/ alongside structure/'s
StructureState — it is descriptive context, not a decision by itself.
"""
