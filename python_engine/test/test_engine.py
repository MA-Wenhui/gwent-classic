"""游戏引擎集成测试"""

import asyncio
from conftest import (
    create_engine_with_decks, simulate_random_game, load_decks, deck_to_args, CARDS_PATH,
    GameEngine, Faction,
)


async def test_game_setup_with_deck():
    """使用预设牌组初始化游戏"""
    engine = create_engine_with_decks(0, 1)
    status = engine.get_status()
    assert status["player1"]["deck_size"] > 0
    assert status["player2"]["deck_size"] > 0
    print(f"  ✅ Setup: decks loaded and initialized")


async def test_game_start_with_deck():
    """使用预设牌组开局抽牌"""
    engine = create_engine_with_decks(0, 1)
    await engine.start_game()

    status = engine.get_status()
    assert status["status"] == "playing"
    assert status["player1"]["hand_size"] == 10
    assert status["player2"]["hand_size"] == 10
    print(f"  ✅ Start: both players drew 10 cards")


async def test_random_play_with_deck():
    """使用预设牌组随机出牌"""
    engine = create_engine_with_decks(2, 3)
    results = await simulate_random_game(engine, max_rounds=1, max_turns_per_round=20)
    assert len(results) >= 1
    print(f"  ✅ Random play: {len(results)} round(s) completed")


async def test_full_game_preset_decks():
    """使用两套预设牌组模拟完整三局对战"""
    engine = create_engine_with_decks(0, 1)
    results = await simulate_random_game(engine, max_rounds=3)

    winner = engine.get_game_winner()
    final = engine.get_status()
    assert final["status"] == "finished"
    assert len(results) >= 1
    print(f"  ✅ Full game ({len(results)} rounds): Winner={winner.name if winner else 'None'}")


async def test_all_deck_matchups():
    """所有预设牌组两两对战（取前4套），验证不崩溃"""
    decks = load_decks()[:4]
    matchups = 0

    for i in range(len(decks)):
        for j in range(i + 1, len(decks)):
            engine = GameEngine(CARDS_PATH)
            p1_f, p1_l, p1_c = deck_to_args(decks[i])
            p2_f, p2_l, p2_c = deck_to_args(decks[j])
            engine.setup_game(
                p1_f, p2_f,
                player1_deck_ids=p1_c, player1_leader_id=p1_l,
                player2_deck_ids=p2_c, player2_leader_id=p2_l,
            )
            await simulate_random_game(engine, max_rounds=3, max_turns_per_round=15)
            matchups += 1

    print(f"  ✅ All matchups: {matchups} games completed without errors")


if __name__ == "__main__":
    print("🎮 Game Engine Integration Tests:")
    asyncio.run(test_game_setup_with_deck())
    asyncio.run(test_game_start_with_deck())
    asyncio.run(test_random_play_with_deck())
    asyncio.run(test_full_game_preset_decks())
    asyncio.run(test_all_deck_matchups())
    print("  All passed!\n")
