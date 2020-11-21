import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, List

import numpy as np
from pathfinding.core.grid import Grid
from pathfinding.finder.dijkstra import DijkstraFinder

from gupb.model.arenas import Arena
from gupb.model.characters import ChampionKnowledge, Facing
from gupb.model.coordinates import Coords, add_coords, sub_coords
from gupb.model.weapons import Weapon, Axe, Sword, Amulet, Knife, Bow

WEAPONS = {
    "bow": Bow(),
    "axe": Axe(),
    "sword": Sword(),
    "knife": Knife(),
    "amulet": Amulet(),
}

WEAPON_TO_INT = {
    "bow": 0,
    "axe": 1,
    "sword": 2,
    "knife": 3,
    "amulet": 4,
}

FACING_TO_INT = {
    Facing.UP: 0,
    Facing.RIGHT: 1,
    Facing.LEFT: 2,
    Facing.DOWN: 3
}

MAX_HEALTH = 5


def weapon_ranking(weapon: Weapon) -> int:
    if isinstance(weapon, Bow):
        return 10
    if isinstance(weapon, Amulet):
        return 8
    if isinstance(weapon, Axe):
        return 6
    if isinstance(weapon, Sword):
        return 6
    return 0


class DistanceMeasure(Enum):
    CLOSE = 0
    FAR = 1
    VERY_FAR = 2
    INACCESSIBLE = 3


@dataclass
class State:
    map_name: int
    x: int
    y: int
    health: int
    visible_enemies: int
    can_attack_enemy: bool
    facing: int
    weapon: int
    distance_to_menhir: int
    tick: int

    @staticmethod
    def get_length():
        return 9

    def as_tuple(self):
        return (
            self.x, self.y, self.health, self.visible_enemies, self.can_attack_enemy,
            self.facing, self.weapon, self.distance_to_menhir, self.tick
        )


def get_state(knowledge: ChampionKnowledge, arena: Arena, tick: int) -> State:
    bot_coords = knowledge.position
    bot_tile = knowledge.visible_tiles.get(bot_coords)
    bot_character = bot_tile.character if bot_tile else None
    bot_weapon = bot_character.weapon.name if bot_character else "knife"
    bot_facing = bot_character.facing if bot_character else Facing.UP

    # ---

    health = bot_character.health if bot_character else 5

    visible_enemies = len([
        coords
        for coords, tile in knowledge.visible_tiles.items()
        if tile.character and coords != bot_coords
    ])

    can_attack_enemy = any(
        coord
        for coord in
        WEAPONS[bot_weapon].cut_positions(arena.terrain, bot_coords, bot_facing)
        if knowledge.visible_tiles[coord].character
    )

    facing = FACING_TO_INT[bot_facing]

    weapon = WEAPON_TO_INT[bot_weapon]

    x, y = sub_coords(bot_coords, arena.menhir_position)
    menhir_distance = np.sqrt(x ** 2 + y ** 2)

    return State(
        hash(arena.name),
        bot_coords[0],
        bot_coords[1],
        health,
        visible_enemies,
        can_attack_enemy,
        facing,
        weapon,
        menhir_distance,
        tick
    )


@dataclass
class Wisdom:
    arena: Arena
    knowledge: Optional[ChampionKnowledge]
    bot_name: str
    grid: Grid
    prev_knowledge: Optional[ChampionKnowledge] = None
    finder = DijkstraFinder()
    t: int = 0

    def next_knowledge(self, knowledge: ChampionKnowledge):
        self.prev_knowledge = self.knowledge
        self.knowledge = knowledge
        self.t += 1

    def get_state(self):
        pass

    @property
    def relative_enemies_positions(self) -> List[float]:
        """
        Returns relative position to the enemies.
         eg.:
            E(0,2)

            B(0,0)    E(4,0)

            E(0,-2)

         B - bot/botelka
         E - enemy
        """

        enemies_coords = [
            coords
            for coords, tile in self.knowledge.visible_tiles.items()
            if tile.character and coords != self.bot_coords
        ]

        relative_enemies_coords = [
            sub_coords(enemy_coord, self.bot_coords)
            for enemy_coord in enemies_coords
        ]

        # Change to format accepted by neural net
        result = [0] * 10  # 10 because of neural net size

        for i in range(len(relative_enemies_coords)):
            x, y = relative_enemies_coords[i]

            result[2 * i] = x
            result[2 * i + 1] = y

        # TODO: Add number of visible tiles to state
        return result

    @property
    def relative_menhir_position(self) -> List[float]:
        menhir_coords = self.arena.menhir_position
        relative_position = sub_coords(menhir_coords, self.bot_coords)

        return [relative_position[0], relative_position[1]]

    @property
    def menhir_distance(self) -> int:
        menhir_coords = self.arena.menhir_position
        m_x, m_y = sub_coords(menhir_coords, self.bot_coords)
        x, y = self.bot_coords

        return int(math.sqrt((x - m_x) ** 2 + (y - m_y) ** 2))

    @property
    def coords_did_not_change(self):
        if not self.prev_knowledge:
            return False
        return self.knowledge.position == self.prev_knowledge.position

    @property
    def bot_coords(self) -> Coords:
        return self.knowledge.position

    @property
    def prev_bot_coords(self) -> Coords:
        return self.prev_knowledge.position

    @property
    def prev_bot_facing(self) -> Facing:
        tile = self.prev_knowledge.visible_tiles[self.bot_coords]

        assert tile.character, "Character must be standing on a tile bot_facing"

        return tile.character.facing

    @property
    def bot_facing(self) -> Facing:
        tile = self.knowledge.visible_tiles[self.bot_coords]

        assert tile.character, "Character must be standing on a tile bot_facing"

        return tile.character.facing

    @property
    def bot_health(self) -> int:
        tile = self.knowledge.visible_tiles[self.bot_coords]

        assert tile.character, "Character must be standing on a tile bot_health"

        return tile.character.health

    @property
    def prev_bot_health(self) -> int:
        if not self.prev_knowledge:
            return MAX_HEALTH
        tile = self.prev_knowledge.visible_tiles[self.prev_bot_coords]

        assert tile.character, "Character must be standing on a tile prev_bot_health"

        return tile.character.health

    @property
    def bot_weapon(self) -> Weapon:
        tile = self.knowledge.visible_tiles[self.bot_coords]

        assert tile.character, "Character must be standing on a tile bot_weapon"

        weapon_name = tile.character.weapon.name

        return WEAPONS[weapon_name]

    @property
    def mist_visible(self) -> bool:
        return any(
            visible_tile
            for visible_tile in self.knowledge.visible_tiles.values()
            if "mist" in {effect.type for effect in visible_tile.effects}
        )

    @property
    def enemies_visible(self) -> bool:
        return any(
            visible_tile
            for visible_tile in self.knowledge.visible_tiles.values()
            if visible_tile.character
        )

    @property
    def better_weapon_visible(self) -> bool:
        return any(
            tile
            for tile in self.knowledge.visible_tiles.values()
            if tile.loot and weapon_ranking(WEAPONS.get(tile.loot.name)) > weapon_ranking(self.bot_weapon)
        )

    @property
    def will_pick_up_worse_weapon(self) -> bool:
        coords_in_front = add_coords(self.bot_coords, self.bot_facing.value)

        if not self.knowledge.visible_tiles[coords_in_front].loot:
            return False

        weapon_in_front = WEAPONS.get(self.knowledge.visible_tiles[coords_in_front].loot.name)

        return weapon_ranking(weapon_in_front) < weapon_ranking(self.bot_weapon)

    @property
    def can_attack_player(self) -> bool:
        return any(
            coord
            for coord in self.bot_weapon.cut_positions(self.arena.terrain, self.bot_coords, self.bot_facing)
            if self.knowledge.visible_tiles[coord].character
        )

    @property
    def distance_to_menhir(self) -> int:
        try:
            steps_num = self.find_path_len(self.arena.menhir_position)
        except Exception:
            # return DistanceMeasure.INACCESSIBLE.value
            return 1000000

        return steps_num
        # if steps_num < 30:
        #     return DistanceMeasure.CLOSE.value
        # if steps_num < 60:
        #     return DistanceMeasure.FAR.value
        # return DistanceMeasure.VERY_FAR.value

    @property
    def lost_health(self):
        return self.bot_health != self.prev_bot_health

    @property
    def reach_menhir_before_mist(self):
        distance = self.distance_to_menhir
        return self.arena.mist_radius / 5 - self.t - 30 > distance

    def find_path_len(self, coords: Coords) -> int:
        steps = 0
        self.grid.cleanup()

        start = self.grid.node(self.bot_coords.x, self.bot_coords.y)
        end = self.grid.node(coords.x, coords.y)

        path, _ = self.finder.find_path(start, end, self.grid)

        facing = self.bot_facing

        for x in range(len(path) - 1):
            actions, facing = self.move_one_tile(facing, path[x], path[x + 1])
            steps += actions

        return steps

    def move_one_tile(self, starting_facing: Facing, coord_0: Coords, coord_1: Coords) -> Tuple[int, Facing]:
        exit_facing = Facing(sub_coords(coord_1, coord_0))

        # Determine what is better, turning left or turning right.
        # Builds 2 lists and compares length.
        facing_turning_left = starting_facing
        left_actions = 0
        while facing_turning_left != exit_facing:
            facing_turning_left = facing_turning_left.turn_left()
            left_actions += 1

        facing_turning_right = starting_facing
        right_actions = 1
        while facing_turning_right != exit_facing:
            facing_turning_right = facing_turning_right.turn_right()
            right_actions += 1

        actions = right_actions if left_actions > right_actions else left_actions
        actions += 1

        return actions, exit_facing
