"""游戏引擎集成测试 - 使用预设牌组 + 随机出牌"""

import sys, os, json, asyncio, random
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from python_engine.logger import setup_logger  # noqa: F401 - 初始化日志
from python_engine import GameEngine, Faction

DECKS_PATH = "python_engine/decks.json"


def load_decks():
    with open(DECKS_PATH) as f:
        return json.load(f)


FACTION_MAP = {
    "realms": Faction.NORTHERN_REALMS,
    "nilfgaard": Faction.NILFGAARD,
    "monsters": Faction.MONSTERS,
    "scoiatael": Faction.SCOIATAEL,
    "skellige": Faction.SKELLIGE,
}


def deck_to_args(deck_data):
    """将 decks.json 条目转为 setup_game 参数"""
    faction = FACTION_MAP[deck_data["faction"]]
    leader_id = deck_data.get("leader")
    card_ids = [tuple(c) for c in deck_data["cards"]]
    return faction, leader_id, card_ids


async def test_game_setup_with_deck():
    """使用预设牌组初始化游戏"""
    decks = load_decks()
    engine = GameEngine("python_engine/cards.json")

    p1_faction, p1_leader, p1_cards = deck_to_args(decks[0])
    p2_faction, p2_leader, p2_cards = deck_to_args(decks[1])

    engine.setup_game(
        p1_faction, p2_faction,
        player1_deck_ids=p1_cards, player1_leader_id=p1_leader,
        player2_deck_ids=p2_cards, player2_leader_id=p2_leader,
    )
    status = engine.get_status()
    assert status["player1"]["faction"] == p1_faction.value
    assert status["player2"]["faction"] == p2_faction.value
    # 部分卡牌 ID 可能在 cards.json 中缺失，只验证牌堆非空
    assert status["player1"]["deck_size"] > 0
    assert status["player2"]["deck_size"] > 0
    print(f"  ✅ Setup: {p1_faction.value}(leader={p1_leader}) vs {p2_faction.value}(leader={p2_leader})")


async def test_game_start_with_deck():
    """使用预设牌组开局抽牌"""
    decks = load_decks()
    engine = GameEngine("python_engine/cards.json")

    p1_faction, p1_leader, p1_cards = deck_to_args(decks[0])
    p2_faction, p2_leader, p2_cards = deck_to_args(decks[1])

    engine.setup_game(
        p1_faction, p2_faction,
        player1_deck_ids=p1_cards, player1_leader_id=p1_leader,
        player2_deck_ids=p2_cards, player2_leader_id=p2_leader,
    )
    await engine.start_game()

    status = engine.get_status()
    assert status["status"] == "playing"
    assert status["player1"]["hand_size"] == 10
    assert status["player2"]["hand_size"] == 10
    print(f"  ✅ Start: both players drew 10 cards")


async def test_random_play_with_deck():
    """使用预设牌组，随机出牌直到手牌耗尽或 pass"""
    decks = load_decks()
    engine = GameEngine("python_engine/cards.json")

    p1_faction, p1_leader, p1_cards = deck_to_args(decks[2])
    p2_faction, p2_leader, p2_cards = deck_to_args(decks[3])

    engine.setup_game(
        p1_faction, p2_faction,
        player1_deck_ids=p1_cards, player1_leader_id=p1_leader,
        player2_deck_ids=p2_cards, player2_leader_id=p2_leader,
    )
    await engine.start_game()

    cards_played = 0
    for _ in range(20):
        player = engine.game_state.current_player
        if player.passed or not player.hand.cards:
            if not player.passed:
                await engine.pass_round(player)
            engine.game_state.current_player = player.opponent
            continue
        card = random.choice(list(player.hand.cards))
        success = await engine.play_card(player, card)
        if success:
            cards_played += 1
        engine.game_state.current_player = player.opponent

    assert cards_played > 0
    print(f"  ✅ Random play: {cards_played} cards played")


async def test_full_game_preset_decks():
    """使用两套预设牌组模拟完整三局对战"""
    decks = load_decks()
    engine = GameEngine("python_engine/cards.json")

    p1_faction, p1_leader, p1_cards = deck_to_args(decks[0])
    p2_faction, p2_leader, p2_cards = deck_to_args(decks[1])

    engine.setup_game(
        p1_faction, p2_faction,
        player1_deck_ids=p1_cards, player1_leader_id=p1_leader,
        player2_deck_ids=p2_cards, player2_leader_id=p2_leader,
    )
    await engine.start_game()

    round_results = []
    for round_num in range(3):
        if not engine.game_state.is_playing:
            break

        turns = 0
        max_turns = 40
        while turns < max_turns:
            player = engine.game_state.current_player
            opponent = player.opponent

            if player.passed and opponent.passed:
                break

            if player.passed:
                engine.game_state.current_player = opponent
                turns += 1
                continue

            if player.hand.cards and random.random() > 0.15:
                card = random.choice(list(player.hand.cards))
                await engine.play_card(player, card)
            else:
                await engine.pass_round(player)

            engine.game_state.current_player = opponent
            turns += 1

        if not engine.game_state.player1.passed:
            await engine.pass_round(engine.game_state.player1)
        if not engine.game_state.player2.passed:
            await engine.pass_round(engine.game_state.player2)

        result = await engine.end_round()
        round_results.append(result)
        winner_name = result.winner.name if result.winner else "Draw"
        print(f"    Round {result.round_number}: P1={result.player1_score} P2={result.player2_score} → {winner_name}")

    winner = engine.get_game_winner()
    final = engine.get_status()
    assert final["status"] == "finished"
    assert len(round_results) >= 1
    print(f"  ✅ Full game ({len(round_results)} rounds): Winner={winner.name if winner else 'None'}")


async def test_all_deck_matchups():
    """所有预设牌组两两对战（取前4套），验证不崩溃"""
    decks = load_decks()[:4]
    matchups = 0

    for i in range(len(decks)):
        for j in range(i + 1, len(decks)):
            engine = GameEngine("python_engine/cards.json")
            p1_f, p1_l, p1_c = deck_to_args(decks[i])
            p2_f, p2_l, p2_c = deck_to_args(decks[j])

            engine.setup_game(
                p1_f, p2_f,
                player1_deck_ids=p1_c, player1_leader_id=p1_l,
                player2_deck_ids=p2_c, player2_leader_id=p2_l,
            )
            await engine.start_game()

            for _ in range(3):
                if not engine.game_state.is_playing:
                    break
                for _ in range(15):
                    player = engine.game_state.current_player
                    if player.passed:
                        engine.game_state.current_player = player.opponent
                        continue
                    if player.hand.cards:
                        card = random.choice(list(player.hand.cards))
                        await engine.play_card(player, card)
                    else:
                        await engine.pass_round(player)
                    engine.game_state.current_player = player.opponent

                if not engine.game_state.player1.passed:
                    await engine.pass_round(engine.game_state.player1)
                if not engine.game_state.player2.passed:
                    await engine.pass_round(engine.game_state.player2)
                await engine.end_round()

            matchups += 1

    print(f"  ✅ All matchups: {matchups} games completed without errors")


if __name__ == "__main__":
    print("🎮 Game Engine Integration Tests (Preset Decks + Random Play):")
    asyncio.run(test_game_setup_with_deck())
    asyncio.run(test_game_start_with_deck())
    asyncio.run(test_random_play_with_deck())
    asyncio.run(test_full_game_preset_decks())
    asyncio.run(test_all_deck_matchups())
    print("  All passed!\n")
