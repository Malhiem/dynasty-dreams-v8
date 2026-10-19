import unittest
from services.league_exit import evict_league_rooms

class Cursor:
    async def to_list(self, _): return [{"_id":"this-draft"}]
class Drafts:
    def find(self,*args): return Cursor()
class DB: drafts=Drafts()
class Manager:
    def get_participants(self,*args): return [("departing",None),("other",None)]
class Socket:
    manager=Manager()
    def __init__(self):
        self.members={"departing":{"personal","league_leaving","draft_this-draft","league_retained","draft_other"},"other":{"league_leaving","draft_this-draft"}}
        self.events=[]
    async def get_session(self,sid): return {"user_id":"user" if sid=="departing" else "other-user"}
    def rooms(self,sid): return list(self.members[sid])
    async def leave_room(self,sid,room): self.members[sid].remove(room)
    async def emit(self,event,payload,to): self.events.append((event,payload,to))
class LeagueExitRooms(unittest.IsolatedAsyncioTestCase):
    async def test_only_departed_league_and_draft_rooms_are_revoked(self):
        sio=Socket();await evict_league_rooms(DB(),sio,"leaving","user")
        self.assertEqual(sio.members['departing'],{'personal','league_retained','draft_other'})
        self.assertEqual(sio.members['other'],{'league_leaving','draft_this-draft'})
        self.assertEqual(len(sio.events),1);self.assertEqual(sio.events[0][2],'departing')
    async def test_disconnected_session_does_not_block_other_sessions(self):
        sio=Socket()
        async def disconnected(sid): raise KeyError(sid)
        sio.get_session=disconnected
        await evict_league_rooms(DB(),sio,'leaving','user')
        self.assertEqual(sio.events,[])
