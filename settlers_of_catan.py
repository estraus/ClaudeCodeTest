#!/usr/bin/env python3
"""
Settlers of Catan - A playable implementation
Play against 3 computer players with medium difficulty AI
"""

import random
from enum import Enum
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict, Counter
import sys


class ResourceType(Enum):
    """Types of resources in the game"""
    WOOD = "Wood"
    BRICK = "Brick"
    SHEEP = "Sheep"
    WHEAT = "Wheat"
    ORE = "Ore"


class TerrainType(Enum):
    """Types of terrain hexes"""
    FOREST = (ResourceType.WOOD, "Forest")
    HILLS = (ResourceType.BRICK, "Hills")
    PASTURE = (ResourceType.SHEEP, "Pasture")
    FIELDS = (ResourceType.WHEAT, "Fields")
    MOUNTAINS = (ResourceType.ORE, "Mountains")
    DESERT = (None, "Desert")

    def __init__(self, resource, display_name):
        self.resource = resource
        self.display_name = display_name


class DevelopmentCardType(Enum):
    """Types of development cards"""
    KNIGHT = "Knight"
    VICTORY_POINT = "Victory Point"
    ROAD_BUILDING = "Road Building"
    YEAR_OF_PLENTY = "Year of Plenty"
    MONOPOLY = "Monopoly"


class BuildingType(Enum):
    """Types of buildings"""
    ROAD = "Road"
    SETTLEMENT = "Settlement"
    CITY = "City"


# Building costs
BUILDING_COSTS = {
    BuildingType.ROAD: {ResourceType.WOOD: 1, ResourceType.BRICK: 1},
    BuildingType.SETTLEMENT: {ResourceType.WOOD: 1, ResourceType.BRICK: 1,
                              ResourceType.SHEEP: 1, ResourceType.WHEAT: 1},
    BuildingType.CITY: {ResourceType.WHEAT: 2, ResourceType.ORE: 3},
}

DEVELOPMENT_CARD_COST = {ResourceType.SHEEP: 1, ResourceType.WHEAT: 1, ResourceType.ORE: 1}


class Hex:
    """Represents a hex tile on the board"""
    def __init__(self, terrain: TerrainType, number: Optional[int], position: Tuple[int, int]):
        self.terrain = terrain
        self.number = number  # 2-12 (except 7), None for desert
        self.position = position
        self.has_robber = (terrain == TerrainType.DESERT)

    def __repr__(self):
        return f"Hex({self.terrain.display_name}, {self.number})"


class Vertex:
    """Represents a vertex (corner) where settlements/cities can be built"""
    def __init__(self, position: Tuple[int, int, int]):
        self.position = position  # Unique identifier for this vertex
        self.building = None  # None, 'settlement', or 'city'
        self.owner = None  # Player index or None
        self.adjacent_hexes: List[Hex] = []  # Hexes touching this vertex
        self.adjacent_vertices: Set[Tuple[int, int, int]] = set()  # Adjacent vertex positions
        self.adjacent_edges: Set[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = set()

    def __repr__(self):
        return f"Vertex({self.position}, {self.building}, owner={self.owner})"


class Edge:
    """Represents an edge where roads can be built"""
    def __init__(self, v1: Tuple[int, int, int], v2: Tuple[int, int, int]):
        # Store vertices in sorted order for consistency
        self.vertices = tuple(sorted([v1, v2]))
        self.owner = None  # Player index or None

    def __repr__(self):
        return f"Edge({self.vertices}, owner={self.owner})"

    def __hash__(self):
        return hash(self.vertices)

    def __eq__(self, other):
        return isinstance(other, Edge) and self.vertices == other.vertices


class Player:
    """Represents a player in the game"""
    def __init__(self, name: str, index: int, is_human: bool = False):
        self.name = name
        self.index = index
        self.is_human = is_human

        # Resources
        self.resources = Counter()

        # Buildings
        self.settlements = []  # List of vertex positions
        self.cities = []  # List of vertex positions
        self.roads = []  # List of edge tuples

        # Development cards
        self.development_cards = []
        self.played_dev_card_this_turn = False

        # Victory points
        self.victory_points = 0
        self.knights_played = 0

        # Special achievements
        self.has_longest_road = False
        self.has_largest_army = False

        # Ports (will be set based on settlement positions)
        self.ports = []  # List of port types

    def get_total_resources(self) -> int:
        """Get total number of resource cards"""
        return sum(self.resources.values())

    def can_afford(self, cost: Dict[ResourceType, int]) -> bool:
        """Check if player can afford a cost"""
        for resource, amount in cost.items():
            if self.resources[resource] < amount:
                return False
        return True

    def pay_resources(self, cost: Dict[ResourceType, int]):
        """Pay resources for a purchase"""
        for resource, amount in cost.items():
            self.resources[resource] -= amount

    def calculate_victory_points(self) -> int:
        """Calculate total victory points"""
        points = 0
        points += len(self.settlements)  # 1 point each
        points += len(self.cities) * 2  # 2 points each
        points += sum(1 for card in self.development_cards if card == DevelopmentCardType.VICTORY_POINT)
        points += 2 if self.has_longest_road else 0
        points += 2 if self.has_largest_army else 0
        return points


class Board:
    """Represents the game board"""
    def __init__(self):
        self.hexes: List[Hex] = []
        self.vertices: Dict[Tuple[int, int, int], Vertex] = {}
        self.edges: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], Edge] = {}
        self.robber_position: Tuple[int, int] = None

        self._setup_standard_board()

    def _setup_standard_board(self):
        """Create a standard Catan board layout"""
        # Simplified board: 19 hexes in a hexagonal pattern
        # Using axial coordinates (q, r)
        hex_positions = [
            # Center
            (0, 0),
            # Ring 1
            (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1),
            # Ring 2
            (2, -1), (2, -2), (1, -2), (0, -2), (-1, -1), (-2, 0),
            (-2, 1), (-2, 2), (-1, 2), (0, 2), (1, 1), (2, 0),
        ]

        # Standard terrain distribution
        terrains = [
            TerrainType.FOREST, TerrainType.FOREST, TerrainType.FOREST, TerrainType.FOREST,
            TerrainType.HILLS, TerrainType.HILLS, TerrainType.HILLS,
            TerrainType.PASTURE, TerrainType.PASTURE, TerrainType.PASTURE, TerrainType.PASTURE,
            TerrainType.FIELDS, TerrainType.FIELDS, TerrainType.FIELDS, TerrainType.FIELDS,
            TerrainType.MOUNTAINS, TerrainType.MOUNTAINS, TerrainType.MOUNTAINS,
            TerrainType.DESERT,
        ]

        # Standard number distribution (no 7)
        numbers = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]

        # Shuffle for randomization
        random.shuffle(terrains)
        random.shuffle(numbers)

        # Create hexes
        number_idx = 0
        for pos in hex_positions:
            terrain = terrains.pop()
            if terrain == TerrainType.DESERT:
                hex_tile = Hex(terrain, None, pos)
                self.robber_position = pos
            else:
                hex_tile = Hex(terrain, numbers[number_idx], pos)
                number_idx += 1
            self.hexes.append(hex_tile)

        # Create vertices and edges (simplified - create vertices for each hex corner)
        self._create_vertices_and_edges()

    def _create_vertices_and_edges(self):
        """Create vertex and edge objects for the board"""
        # For each hex, create 6 vertices at corners
        # Using cube coordinates for vertices: (x, y, z) where x + y + z = 0

        vertex_positions = set()

        for hex_tile in self.hexes:
            q, r = hex_tile.position
            # Calculate the 6 vertex positions around this hex
            hex_vertices = self._get_hex_vertices(q, r)
            for v_pos in hex_vertices:
                vertex_positions.add(v_pos)
                if v_pos not in self.vertices:
                    self.vertices[v_pos] = Vertex(v_pos)
                self.vertices[v_pos].adjacent_hexes.append(hex_tile)

        # Create edges between adjacent vertices
        for v_pos in vertex_positions:
            adjacent = self._get_adjacent_vertex_positions(v_pos)
            for adj_pos in adjacent:
                if adj_pos in vertex_positions:
                    edge_key = tuple(sorted([v_pos, adj_pos]))
                    if edge_key not in self.edges:
                        self.edges[edge_key] = Edge(v_pos, adj_pos)
                    self.vertices[v_pos].adjacent_vertices.add(adj_pos)
                    self.vertices[v_pos].adjacent_edges.add(edge_key)

    def _get_hex_vertices(self, q: int, r: int) -> List[Tuple[int, int, int]]:
        """Get the 6 vertex positions for a hex at axial coordinates (q, r)"""
        # Convert axial to cube coordinates for the hex center
        # Then calculate vertex positions around it
        vertices = []
        # Simplified vertex calculation - each hex corner
        for i in range(6):
            angle = i * 60  # degrees
            # Create unique vertex positions
            v = (q * 2 + (i // 3), r * 2 + (i % 3), i)
            vertices.append(v)
        return vertices

    def _get_adjacent_vertex_positions(self, v_pos: Tuple[int, int, int]) -> List[Tuple[int, int, int]]:
        """Get positions of vertices adjacent to this vertex"""
        # Simplified - return potential adjacent positions
        x, y, z = v_pos
        return [
            (x + 1, y, z), (x - 1, y, z),
            (x, y + 1, z), (x, y - 1, z),
            (x, y, z + 1), (x, y, z - 1),
        ]

    def get_hex_by_position(self, position: Tuple[int, int]) -> Optional[Hex]:
        """Get hex at given position"""
        for hex_tile in self.hexes:
            if hex_tile.position == position:
                return hex_tile
        return None


class Game:
    """Main game class"""
    def __init__(self):
        self.board = Board()
        self.players: List[Player] = []
        self.current_player_idx = 0
        self.turn_number = 0
        self.game_phase = "setup"  # setup, main_game, ended

        # Development cards deck
        self.dev_card_deck = self._create_dev_card_deck()
        random.shuffle(self.dev_card_deck)

        # Track longest road and largest army
        self.longest_road_length = 4  # Minimum to claim
        self.longest_road_player = None
        self.largest_army_size = 2  # Minimum to claim
        self.largest_army_player = None

        # Setup phase tracking
        self.setup_round = 1  # Round 1: forward, Round 2: backward
        self.setup_settlements_placed = 0

    def _create_dev_card_deck(self) -> List[DevelopmentCardType]:
        """Create the development card deck"""
        deck = []
        deck += [DevelopmentCardType.KNIGHT] * 14
        deck += [DevelopmentCardType.VICTORY_POINT] * 5
        deck += [DevelopmentCardType.ROAD_BUILDING] * 2
        deck += [DevelopmentCardType.YEAR_OF_PLENTY] * 2
        deck += [DevelopmentCardType.MONOPOLY] * 2
        return deck

    def add_player(self, name: str, is_human: bool = False):
        """Add a player to the game"""
        player = Player(name, len(self.players), is_human)
        self.players.append(player)

    def roll_dice(self) -> Tuple[int, int]:
        """Roll two dice"""
        return (random.randint(1, 6), random.randint(1, 6))

    def distribute_resources(self, dice_sum: int):
        """Distribute resources based on dice roll"""
        if dice_sum == 7:
            return  # Robber - no resources

        # Find all hexes with the rolled number
        for hex_tile in self.board.hexes:
            if hex_tile.number == dice_sum and not hex_tile.has_robber:
                resource = hex_tile.terrain.resource
                if resource is None:
                    continue

                # Find all vertices touching this hex
                for vertex in self.board.vertices.values():
                    if hex_tile in vertex.adjacent_hexes and vertex.owner is not None:
                        # Give resources to the owner
                        player = self.players[vertex.owner]
                        if vertex.building == "settlement":
                            player.resources[resource] += 1
                        elif vertex.building == "city":
                            player.resources[resource] += 2

    def can_build_settlement(self, player: Player, vertex_pos: Tuple[int, int, int]) -> bool:
        """Check if player can build a settlement at vertex"""
        if vertex_pos not in self.board.vertices:
            return False

        vertex = self.board.vertices[vertex_pos]

        # Check if vertex is empty
        if vertex.building is not None:
            return False

        # Check distance rule (no adjacent settlements)
        for adj_pos in vertex.adjacent_vertices:
            if adj_pos in self.board.vertices:
                adj_vertex = self.board.vertices[adj_pos]
                if adj_vertex.building is not None:
                    return False

        # Check if player has a connecting road (not in setup phase)
        if self.game_phase != "setup":
            has_connecting_road = False
            for edge_key in vertex.adjacent_edges:
                if edge_key in self.board.edges:
                    edge = self.board.edges[edge_key]
                    if edge.owner == player.index:
                        has_connecting_road = True
                        break
            if not has_connecting_road:
                return False

        return True

    def build_settlement(self, player: Player, vertex_pos: Tuple[int, int, int]):
        """Build a settlement"""
        vertex = self.board.vertices[vertex_pos]
        vertex.building = "settlement"
        vertex.owner = player.index
        player.settlements.append(vertex_pos)

    def can_build_road(self, player: Player, edge_key: Tuple[Tuple[int, int, int], Tuple[int, int, int]]) -> bool:
        """Check if player can build a road on edge"""
        if edge_key not in self.board.edges:
            return False

        edge = self.board.edges[edge_key]

        # Check if edge is empty
        if edge.owner is not None:
            return False

        # Check if player has an adjacent road or settlement/city
        v1, v2 = edge.vertices
        for v_pos in [v1, v2]:
            if v_pos in self.board.vertices:
                vertex = self.board.vertices[v_pos]
                # Check if player has a settlement/city here
                if vertex.owner == player.index:
                    return True
                # Check if player has an adjacent road
                for adj_edge_key in vertex.adjacent_edges:
                    if adj_edge_key != edge_key and adj_edge_key in self.board.edges:
                        if self.board.edges[adj_edge_key].owner == player.index:
                            return True

        return False

    def build_road(self, player: Player, edge_key: Tuple[Tuple[int, int, int], Tuple[int, int, int]]):
        """Build a road"""
        edge = self.board.edges[edge_key]
        edge.owner = player.index
        player.roads.append(edge_key)

    def can_build_city(self, player: Player, vertex_pos: Tuple[int, int, int]) -> bool:
        """Check if player can build a city at vertex"""
        if vertex_pos not in self.board.vertices:
            return False

        vertex = self.board.vertices[vertex_pos]

        # Check if player owns a settlement here
        if vertex.building != "settlement" or vertex.owner != player.index:
            return False

        return True

    def build_city(self, player: Player, vertex_pos: Tuple[int, int, int]):
        """Upgrade settlement to city"""
        vertex = self.board.vertices[vertex_pos]
        vertex.building = "city"
        player.settlements.remove(vertex_pos)
        player.cities.append(vertex_pos)

    def calculate_longest_road(self, player: Player) -> int:
        """Calculate the longest road for a player using DFS"""
        if len(player.roads) < 5:
            return 0

        # Build adjacency graph of roads
        road_graph = defaultdict(list)
        for edge_key in player.roads:
            v1, v2 = edge_key
            road_graph[v1].append(v2)
            road_graph[v2].append(v1)

        # DFS from each vertex to find longest path
        max_length = 0
        for start_vertex in road_graph:
            visited = set()
            length = self._dfs_longest_road(start_vertex, road_graph, visited)
            max_length = max(max_length, length)

        return max_length

    def _dfs_longest_road(self, vertex, graph, visited) -> int:
        """DFS helper for longest road calculation"""
        visited.add(vertex)
        max_length = 0

        for neighbor in graph[vertex]:
            if neighbor not in visited:
                length = 1 + self._dfs_longest_road(neighbor, graph, visited)
                max_length = max(max_length, length)

        visited.remove(vertex)
        return max_length

    def update_longest_road(self):
        """Update longest road ownership"""
        for player in self.players:
            road_length = self.calculate_longest_road(player)
            if road_length >= self.longest_road_length:
                if road_length > self.longest_road_length or self.longest_road_player is None:
                    # Remove from previous holder
                    if self.longest_road_player is not None:
                        self.players[self.longest_road_player].has_longest_road = False
                    # Assign to new holder
                    self.longest_road_length = road_length
                    self.longest_road_player = player.index
                    player.has_longest_road = True

    def update_largest_army(self):
        """Update largest army ownership"""
        for player in self.players:
            if player.knights_played >= self.largest_army_size:
                if player.knights_played > self.largest_army_size or self.largest_army_player is None:
                    # Remove from previous holder
                    if self.largest_army_player is not None:
                        self.players[self.largest_army_player].has_largest_army = False
                    # Assign to new holder
                    self.largest_army_size = player.knights_played
                    self.largest_army_player = player.index
                    player.has_largest_army = True

    def check_victory(self) -> Optional[Player]:
        """Check if any player has won"""
        for player in self.players:
            player.victory_points = player.calculate_victory_points()
            if player.victory_points >= 10:
                return player
        return None


class AI:
    """AI player logic (medium difficulty)"""

    @staticmethod
    def take_turn(game: Game, player: Player):
        """AI takes its turn"""
        print(f"\n{player.name}'s turn...")

        # Roll dice (done by main game loop)
        # This method handles the player's actions after rolling

        # AI Strategy (medium difficulty):
        # 1. Build cities if possible (high priority)
        # 2. Build settlements if possible (high priority)
        # 3. Build roads towards good spots (medium priority)
        # 4. Buy development cards if resources available (low priority)
        # 5. Trade with bank if needed (4:1 or 3:1 if has port)

        actions_taken = []

        # Try to build a city
        if player.can_afford(BUILDING_COSTS[BuildingType.CITY]) and player.settlements:
            vertex_pos = player.settlements[0]
            if game.can_build_city(player, vertex_pos):
                player.pay_resources(BUILDING_COSTS[BuildingType.CITY])
                game.build_city(player, vertex_pos)
                actions_taken.append(f"Built a city at {vertex_pos}")

        # Try to build a settlement
        if player.can_afford(BUILDING_COSTS[BuildingType.SETTLEMENT]):
            # Find valid settlement locations
            valid_positions = []
            for vertex_pos, vertex in game.board.vertices.items():
                if game.can_build_settlement(player, vertex_pos):
                    # Score this position based on adjacent hex resources
                    score = AI._score_settlement_position(vertex)
                    valid_positions.append((score, vertex_pos))

            if valid_positions:
                # Build at best position
                valid_positions.sort(reverse=True)
                _, best_pos = valid_positions[0]
                player.pay_resources(BUILDING_COSTS[BuildingType.SETTLEMENT])
                game.build_settlement(player, best_pos)
                actions_taken.append(f"Built a settlement")

        # Try to build roads (up to 2 per turn)
        roads_built = 0
        while roads_built < 2 and player.can_afford(BUILDING_COSTS[BuildingType.ROAD]):
            # Find valid road locations
            valid_edges = []
            for edge_key, edge in game.board.edges.items():
                if game.can_build_road(player, edge_key):
                    # Score based on expansion potential
                    score = AI._score_road_position(game, player, edge_key)
                    valid_edges.append((score, edge_key))

            if valid_edges:
                valid_edges.sort(reverse=True)
                _, best_edge = valid_edges[0]
                player.pay_resources(BUILDING_COSTS[BuildingType.ROAD])
                game.build_road(player, best_edge)
                roads_built += 1
                actions_taken.append(f"Built a road")
            else:
                break

        # Try to buy a development card
        if player.can_afford(DEVELOPMENT_CARD_COST) and game.dev_card_deck:
            player.pay_resources(DEVELOPMENT_CARD_COST)
            card = game.dev_card_deck.pop()
            player.development_cards.append(card)
            actions_taken.append(f"Bought a development card")

        # Consider trading with bank (simplified - just trade excess resources)
        AI._trade_with_bank(player)

        if actions_taken:
            for action in actions_taken:
                print(f"  - {action}")
        else:
            print(f"  - No actions taken")

    @staticmethod
    def _score_settlement_position(vertex: Vertex) -> float:
        """Score a potential settlement position"""
        score = 0.0
        resource_diversity = set()

        for hex_tile in vertex.adjacent_hexes:
            if hex_tile.terrain.resource is not None:
                resource_diversity.add(hex_tile.terrain.resource)
                # Score based on number probability
                if hex_tile.number:
                    # 6 and 8 are best (5 ways to roll)
                    # 5 and 9 are good (4 ways)
                    # etc.
                    prob_map = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
                    score += prob_map.get(hex_tile.number, 0)

        # Bonus for resource diversity
        score += len(resource_diversity) * 2

        return score

    @staticmethod
    def _score_road_position(game: Game, player: Player, edge_key) -> float:
        """Score a potential road position"""
        score = 0.0
        v1, v2 = edge_key

        # Check if road leads to a good settlement spot
        for v_pos in [v1, v2]:
            if v_pos in game.board.vertices:
                vertex = game.board.vertices[v_pos]
                if vertex.building is None:
                    # Check if we could build here (ignoring road requirement)
                    can_build = True
                    for adj_pos in vertex.adjacent_vertices:
                        if adj_pos in game.board.vertices:
                            adj_vertex = game.board.vertices[adj_pos]
                            if adj_vertex.building is not None:
                                can_build = False
                                break

                    if can_build:
                        score += AI._score_settlement_position(vertex)

        return score

    @staticmethod
    def _trade_with_bank(player: Player):
        """Simple bank trading logic"""
        # If we have excess of one resource (>5), trade it for something we need
        # For simplicity, just trade excess for missing resources in building costs
        pass

    @staticmethod
    def choose_initial_settlement(game: Game, player: Player) -> Optional[Tuple[int, int, int]]:
        """AI chooses initial settlement position"""
        valid_positions = []

        for vertex_pos, vertex in game.board.vertices.items():
            if game.can_build_settlement(player, vertex_pos):
                score = AI._score_settlement_position(vertex)
                valid_positions.append((score, vertex_pos))

        if valid_positions:
            valid_positions.sort(reverse=True)
            # Add some randomness for medium difficulty
            # Choose from top 5 positions
            top_positions = valid_positions[:min(5, len(valid_positions))]
            _, chosen_pos = random.choice(top_positions)
            return chosen_pos

        return None

    @staticmethod
    def choose_initial_road(game: Game, player: Player, settlement_pos: Tuple[int, int, int]) -> Optional[Tuple]:
        """AI chooses initial road position adjacent to settlement"""
        vertex = game.board.vertices[settlement_pos]
        valid_edges = []

        for edge_key in vertex.adjacent_edges:
            if edge_key in game.board.edges:
                edge = game.board.edges[edge_key]
                if edge.owner is None:
                    score = AI._score_road_position(game, player, edge_key)
                    valid_edges.append((score, edge_key))

        if valid_edges:
            valid_edges.sort(reverse=True)
            _, chosen_edge = valid_edges[0]
            return chosen_edge

        return None


class GameUI:
    """CLI interface for the game"""

    @staticmethod
    def display_game_state(game: Game):
        """Display current game state"""
        print("\n" + "=" * 60)
        print(f"Turn {game.turn_number} - {game.players[game.current_player_idx].name}'s turn")
        print("=" * 60)

        # Display player info
        for i, player in enumerate(game.players):
            marker = ">>>" if i == game.current_player_idx else "   "
            resources_total = player.get_total_resources()
            print(f"{marker} {player.name}: {player.calculate_victory_points()} VP | "
                  f"{len(player.settlements)} settlements | {len(player.cities)} cities | "
                  f"{len(player.roads)} roads | {resources_total} resources")

        print()

    @staticmethod
    def display_resources(player: Player):
        """Display player's resources"""
        print(f"\n{player.name}'s Resources:")
        for resource_type in ResourceType:
            count = player.resources[resource_type]
            if count > 0:
                print(f"  {resource_type.value}: {count}")
        print(f"Total: {player.get_total_resources()}")

    @staticmethod
    def display_board_summary(game: Game):
        """Display a summary of the board"""
        print("\nBoard Summary:")
        print(f"Total hexes: {len(game.board.hexes)}")
        print(f"Robber at: {game.board.robber_position}")

        # Show hex distribution
        terrain_counts = defaultdict(int)
        for hex_tile in game.board.hexes:
            terrain_counts[hex_tile.terrain.display_name] += 1

        for terrain, count in terrain_counts.items():
            print(f"  {terrain}: {count}")

    @staticmethod
    def get_player_action(game: Game, player: Player) -> str:
        """Get action from human player"""
        GameUI.display_resources(player)

        print("\nAvailable actions:")
        print("  1. Build road")
        print("  2. Build settlement")
        print("  3. Build city")
        print("  4. Buy development card")
        print("  5. Trade with bank")
        print("  6. End turn")

        choice = input("\nChoose action (1-6): ").strip()
        return choice

    @staticmethod
    def handle_human_turn(game: Game, player: Player):
        """Handle human player's turn"""
        while True:
            choice = GameUI.get_player_action(game, player)

            if choice == "6":
                break
            elif choice == "1":
                GameUI.handle_build_road(game, player)
            elif choice == "2":
                GameUI.handle_build_settlement(game, player)
            elif choice == "3":
                GameUI.handle_build_city(game, player)
            elif choice == "4":
                GameUI.handle_buy_dev_card(game, player)
            elif choice == "5":
                print("Trading not implemented in this version")
            else:
                print("Invalid choice")

    @staticmethod
    def handle_build_road(game: Game, player: Player):
        """Handle building a road"""
        if not player.can_afford(BUILDING_COSTS[BuildingType.ROAD]):
            print("Not enough resources!")
            return

        print("\nAvailable road positions:")
        valid_edges = []
        for i, (edge_key, edge) in enumerate(game.board.edges.items()):
            if game.can_build_road(player, edge_key):
                valid_edges.append(edge_key)
                print(f"  {i + 1}. Edge {edge_key}")

        if not valid_edges:
            print("No valid positions!")
            return

        try:
            choice = int(input(f"Choose position (1-{len(valid_edges)}): ")) - 1
            if 0 <= choice < len(valid_edges):
                edge_key = valid_edges[choice]
                player.pay_resources(BUILDING_COSTS[BuildingType.ROAD])
                game.build_road(player, edge_key)
                print("Road built!")
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")

    @staticmethod
    def handle_build_settlement(game: Game, player: Player):
        """Handle building a settlement"""
        if not player.can_afford(BUILDING_COSTS[BuildingType.SETTLEMENT]):
            print("Not enough resources!")
            return

        print("\nAvailable settlement positions:")
        valid_positions = []
        for i, (vertex_pos, vertex) in enumerate(game.board.vertices.items()):
            if game.can_build_settlement(player, vertex_pos):
                valid_positions.append(vertex_pos)
                score = AI._score_settlement_position(vertex)
                print(f"  {i + 1}. Position {vertex_pos} (score: {score:.1f})")

        if not valid_positions:
            print("No valid positions!")
            return

        try:
            choice = int(input(f"Choose position (1-{len(valid_positions)}): ")) - 1
            if 0 <= choice < len(valid_positions):
                vertex_pos = valid_positions[choice]
                player.pay_resources(BUILDING_COSTS[BuildingType.SETTLEMENT])
                game.build_settlement(player, vertex_pos)
                print("Settlement built!")
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")

    @staticmethod
    def handle_build_city(game: Game, player: Player):
        """Handle building a city"""
        if not player.can_afford(BUILDING_COSTS[BuildingType.CITY]):
            print("Not enough resources!")
            return

        if not player.settlements:
            print("You need a settlement to upgrade!")
            return

        print("\nYour settlements:")
        for i, vertex_pos in enumerate(player.settlements):
            print(f"  {i + 1}. Position {vertex_pos}")

        try:
            choice = int(input(f"Choose settlement (1-{len(player.settlements)}): ")) - 1
            if 0 <= choice < len(player.settlements):
                vertex_pos = player.settlements[choice]
                player.pay_resources(BUILDING_COSTS[BuildingType.CITY])
                game.build_city(player, vertex_pos)
                print("City built!")
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")

    @staticmethod
    def handle_buy_dev_card(game: Game, player: Player):
        """Handle buying a development card"""
        if not player.can_afford(DEVELOPMENT_CARD_COST):
            print("Not enough resources!")
            return

        if not game.dev_card_deck:
            print("No development cards left!")
            return

        player.pay_resources(DEVELOPMENT_CARD_COST)
        card = game.dev_card_deck.pop()
        player.development_cards.append(card)
        print(f"You bought a development card!")
        if card != DevelopmentCardType.VICTORY_POINT:
            print(f"It's a {card.value}")


def play_game():
    """Main game loop"""
    print("=" * 60)
    print("SETTLERS OF CATAN")
    print("=" * 60)
    print("\nWelcome! You will play against 3 computer players.")
    print("First to 10 victory points wins!\n")

    # Initialize game
    game = Game()

    # Add players
    player_name = input("Enter your name: ").strip()
    if not player_name:
        player_name = "You"

    game.add_player(player_name, is_human=True)
    game.add_player("AI Player 1", is_human=False)
    game.add_player("AI Player 2", is_human=False)
    game.add_player("AI Player 3", is_human=False)

    print(f"\nPlayers: {', '.join(p.name for p in game.players)}")
    input("\nPress Enter to start...")

    # Setup phase - each player places 2 settlements and 2 roads
    print("\n" + "=" * 60)
    print("SETUP PHASE")
    print("=" * 60)
    print("Each player will place 2 settlements and 2 roads.")
    print("In the second round, you'll get resources from your second settlement.")

    # Round 1: forward order
    for player in game.players:
        print(f"\n{player.name} - Place your first settlement")

        if player.is_human:
            GameUI.display_board_summary(game)
            print("\nChoosing best settlement positions for you...")
            settlement_pos = AI.choose_initial_settlement(game, player)
        else:
            settlement_pos = AI.choose_initial_settlement(game, player)

        if settlement_pos:
            game.build_settlement(player, settlement_pos)
            print(f"Settlement placed at {settlement_pos}")

            # Place road
            print(f"{player.name} - Place your first road")
            road_pos = AI.choose_initial_road(game, player, settlement_pos)
            if road_pos:
                game.build_road(player, road_pos)
                print(f"Road placed")

    # Round 2: backward order (with resource distribution)
    for player in reversed(game.players):
        print(f"\n{player.name} - Place your second settlement")

        if player.is_human:
            print("\nChoosing best settlement position for you...")

        settlement_pos = AI.choose_initial_settlement(game, player)
        if settlement_pos:
            game.build_settlement(player, settlement_pos)
            print(f"Settlement placed at {settlement_pos}")

            # Give starting resources from this settlement
            vertex = game.board.vertices[settlement_pos]
            for hex_tile in vertex.adjacent_hexes:
                if hex_tile.terrain.resource is not None:
                    player.resources[hex_tile.terrain.resource] += 1
                    print(f"Received 1 {hex_tile.terrain.resource.value}")

            # Place road
            print(f"{player.name} - Place your second road")
            road_pos = AI.choose_initial_road(game, player, settlement_pos)
            if road_pos:
                game.build_road(player, road_pos)
                print(f"Road placed")

    # Main game phase
    game.game_phase = "main_game"
    print("\n" + "=" * 60)
    print("MAIN GAME")
    print("=" * 60)
    input("\nPress Enter to continue...")

    # Main game loop
    while game.game_phase == "main_game":
        game.turn_number += 1
        player = game.players[game.current_player_idx]

        GameUI.display_game_state(game)

        # Roll dice
        if player.is_human:
            input(f"\n{player.name}, press Enter to roll dice...")

        die1, die2 = game.roll_dice()
        dice_sum = die1 + die2
        print(f"\n{player.name} rolled: {die1} + {die2} = {dice_sum}")

        if dice_sum == 7:
            print("Robber! (Simplified - skipping robber movement)")
            # In full game, players with >7 cards discard half, then move robber
        else:
            # Distribute resources
            game.distribute_resources(dice_sum)
            print("Resources distributed")

        # Player's turn
        if player.is_human:
            GameUI.handle_human_turn(game, player)
        else:
            AI.take_turn(game, player)

        # Update special achievements
        game.update_longest_road()
        game.update_largest_army()

        # Check for victory
        winner = game.check_victory()
        if winner:
            print("\n" + "=" * 60)
            print(f"🎉 {winner.name} WINS! 🎉")
            print("=" * 60)
            print(f"\nFinal Score: {winner.victory_points} Victory Points")
            print(f"  Settlements: {len(winner.settlements)}")
            print(f"  Cities: {len(winner.cities)}")
            print(f"  Longest Road: {'Yes' if winner.has_longest_road else 'No'}")
            print(f"  Largest Army: {'Yes' if winner.has_largest_army else 'No'}")
            game.game_phase = "ended"
            break

        # Next player
        game.current_player_idx = (game.current_player_idx + 1) % len(game.players)

        # Pause between turns
        if not player.is_human:
            input("\nPress Enter for next turn...")


if __name__ == "__main__":
    try:
        play_game()
    except KeyboardInterrupt:
        print("\n\nGame interrupted. Thanks for playing!")
        sys.exit(0)
