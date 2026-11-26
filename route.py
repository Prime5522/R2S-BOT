import re

from aiohttp import web
from asyncio import sleep

from database.clonedb import clone_db

routes = web.RouteTableDef()

# ওয়েবসাইট (Cloudflare Pages) অন্য ডোমেইন থেকে এই API কল করে, তাই CORS খোলা
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "no-store",
}


@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("Made with MR.PRIME")


@routes.get("/api/bot")
async def api_bot(request):
    """
    ✨ পার্মানেন্ট লিংকের ওয়েবসাইট জিজ্ঞেস করে: "এই কোডের বট এখন কোনটা?"
    উত্তর: {"ok": true, "bot": "ক্লোনের_ইউজারনেম"} — মূল বটের কোড হলে "bot": null।
    ক্লোন বট বদলালে (Change Bot) ডাটাবেসের নাম বদলায়, তাই সব পুরনো লিংক নিজে থেকে নতুন বটে যায়।
    """
    code = request.query.get("code", "")
    if not re.fullmatch(r"[A-Za-z0-9]{16,64}", code):
        return web.json_response({"ok": False}, headers=CORS)
    username = None
    try:
        bot_id = await clone_db.get_link_bot(code)
        if bot_id:
            doc = await clone_db.get_clone(bot_id)
            if doc:
                username = doc.get("bot_username")
    except Exception as e:
        print(f"[api/bot] lookup failed: {e!r}")
        return web.json_response({"ok": False}, headers=CORS)
    return web.json_response({"ok": True, "bot": username}, headers=CORS)


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app
