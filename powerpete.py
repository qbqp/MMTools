import colorsys
import sys

import pygame
from pygame.locals import *


# 0xd5 = ??? (a ton) of tiles repeated
# 0x84 = tile repeated 7 times (???) (assume 3 are added, because you wouldn't repeat a tile just twice?)
# 0x14 (20) = next 21 tiles are as-is

pygame.font.init()
# print(pygame.font.get_fonts())
# sys.exit(0)

# Border.image
# Definitely uncompressed
# CLUT looks like it starts immediately after this header
# 00 04 B6 04 00 00 00 02

# BargainScene.image
# probably compressed
# 00 04 B6 04 00 00 00 00

# bargain1.shapes
# probably compressed
# 00 05 B0 8A 00 00 00 00

# Jurassic.tileset
# 00 09 DB 6B 00 00 00 00 01

# Candy.tileset
# 00 09 D3 03 00 00 00 00 01

# Fairy.Tileset
# 00 0B B7 8B 00 00 00 00 01

# Clown.tileset
# 00 09 82 93 00 00 00 00 01

# Bargain.tileset
# 00 0B C9 DD 00 00 00 00 01

class Utils:

    # This should take a list and an offset instead of having the caller do that
    @staticmethod
    def read_short(data):
        return (data[0] << 8) + data[1]

    @staticmethod
    def read_short_2(data, offset):
        return (data[offset] << 8) + data[offset + 1]

    @staticmethod
    def read_clut(data):
        i = 0
        colors = []
        while i < len(data):
            colors.append((
                Utils.read_short(data[i: i + 2]) / 256.0,
                Utils.read_short(data[i + 2: i + 4]) / 256.0,
                Utils.read_short(data[i + 4: i + 6]) / 256.0))

            i += 6

        return colors

    @staticmethod
    def read_image(data, clut, size):
        # print(size)
        width, height = size
        surface = pygame.Surface(size)
        pixel_array = pygame.PixelArray(surface)

        i = 0
        for y in range(height):
            for x in range(width):
                pixel_array[x, y] = clut[data[i]]
                i += 1

        pixel_array.close()

        return surface

    @staticmethod
    def read_tile_index_list(data, offset):
        count = Utils.read_short_2(data, offset)
        offset += 2

        tile_indices = []
        for i in range(count):
            tile_indices.append(Utils.read_short_2(data, offset))
            offset += 2

        return tile_indices, offset


    @staticmethod
    def unpack_generic(data):
        compression_type = data[0x07]
        if compression_type == 0 or compression_type == 1:
            return data[0 : 0x08] + Utils.unpack_type_1(data[0x08 : ])
        elif compression_type == 6:
            return data[0 : 0x08] + Utils.unpack_type_2(data[0x08 : ])

    # images, tilesets, runs happen in multiples of 1
    @staticmethod
    def unpack_type_1(data):
        i = 0
        output = []
        while i < len(data):
            current_byte = data[i]
            if current_byte > 0x80:
                # 0xf7 = repeat 10 times
                # 0xfd = repeat 4 times
                repeat_count = 0xff - current_byte + 2
                output += [data[i + 1]] * repeat_count
                i += 2
            else:
                # 01 = skip 2
                skip_count = current_byte + 1
                output += data[i + 1 : i + skip_count + 1]
                i += skip_count + 1
        return bytes(output)

    # maps, runs happen in multiples of 2
    @staticmethod
    def unpack_type_2(data):
        i = 0
        output = []

        while i < len(data):
            current_byte = data[i]

            # repeat
            if current_byte & 0x80:
                repeat_count = current_byte - 0x80 + 1
                tile = (data[i + 1] << 8) + data[i + 2]
                output += [tile] * repeat_count

                i += 3

            # next N + 1 tiles are is-is
            else:
                for j in range(current_byte + 1):
                    next_tile = (data[i + (j * 2) + 1] << 8) + data[i + (j * 2) + 2]
                    output.append(next_tile)

                i += (j + 1) * 2 + 1

        return output

class PPImage:
    def __init__(self, filename):
        # 4 bytes, always 0x0004b604
        # 4 bytes, 0x00000002 for uncompressed, 0x00000000 for compressed
        # 1536 bytes CLUT
        # 2 byte width
        # 2 byte height
        # image data

        with open(filename, "rb") as file_handle:
            raw_data = Utils.unpack_generic(file_handle.read())

        self.clut = Utils.read_clut(raw_data[0x8 : 0x608])
        self.width = Utils.read_short(raw_data[0x608 : 0x60a])
        self.height = Utils.read_short(raw_data[0x60a : 0x60c])
        # print(self.width)

        self.image = Utils.read_image(raw_data[0x60c :], self.clut, (self.width, self.height))

class PPTileSet:
    def __init__(self, filename, clut):
        # after tile images:
        # 2 bytes, length of next section
        # N records, 2 bytes each, that look like indices of tiles
        # 2 bytes, length of next section
        # N records, 8 bytes each, flags?
        # 0x0100
        # Something that looks like a CLUT
        # Then at the end, animation data?

        with open(filename, "rb") as file_handle:
            self.raw_data = Utils.unpack_generic(file_handle.read())

        filename_count = Utils.read_short(self.raw_data[0x26 : 0x28])

        tile_count_offset = 0x28 + (filename_count * 0x100)
        # print(tile_count_offset)

        tile_count = Utils.read_short(self.raw_data[tile_count_offset : tile_count_offset + 2])
        # print(tile_count)
        self.tiles = []

        # offset = 0x42a
        offset = tile_count_offset + 2
        for i in range(tile_count):
            self.tiles.append(Utils.read_image(self.raw_data[offset + (i * (32 * 32)) : offset + (i * (32 * 32)) + (32 * 32)], clut, (32, 32)))

        offset += tile_count * 32 * 32

        self.tile_index_list, offset = Utils.read_tile_index_list(self.raw_data, offset)

        # width = 640
        # height = 1024
        #
        # screen = pygame.display.set_mode((width, height))
        # pygame.display.set_caption("Tile Viewer")
        # running = True
        #
        # try:
        #     i = 0
        #     y = 0
        #     while y < height:
        #         x = 0
        #         while x < width:
        #             screen.blit(self.tiles[self.tile_index_list[i]], (x, y))
        #             x += 32
        #             i += 1
        #
        #         y +=32
        # except IndexError:
        #     pass
        #
        # pygame.display.update()
        #
        # while running:
        #     for event in pygame.event.get():
        #         if event.type == QUIT:
        #             running = False
        #
        # pygame.quit()

    def get_tile(self, tile_index):
        try:
            return self.tiles[self.tile_index_list[tile_index]]
        except IndexError:
            print(tile_index)
            return self.tiles[0]

    @staticmethod
    def read_tile(data):
        if len(data) != 32 * 32:
            raise Exception("Invalid tile length")

        i = 0
        surface = pygame.Surface((32, 32))
        pixel_array = pygame.PixelArray(surface)

        for y in range(32):
            for x in range(32):
                current_byte = data[i]
                color = (current_byte, current_byte, current_byte)
                pixel_array[x, y] = color
                i += 1

        pixel_array.close()

        return surface



class TileSet:
    def __init__(self):
        self._tiles = []
        myfont = pygame.font.SysFont('couriernew', 10)

        for i in range(0xffff):
            tile = pygame.Surface((32, 32))

            # These don't work that well
            # color_fraction = float(i) / float(0xffff)
            # value = (i >> 8) / 255.0
            # color = colorsys.hsv_to_rgb(color_fraction, 1.0, value)

            # color = [e * 255.0 for e in color]

            if i & 0x8000:
                green = 255
            else:
                green = 0

            pygame.draw.rect(tile, (i >> 8, green, i % 0xff), pygame.Rect(0, 0, 32, 32))
            # pygame.draw.rect(tile, color, pygame.Rect(0, 0, 32, 32))

            text_surface = myfont.render(hex(i)[2:], True, (0xff, 0xff, 0xff))
            tile.blit(text_surface, (0, 0))

            # tile.fill((0xff, 0, 0))
            self._tiles.append(tile)

    def get_tile(self, i) -> pygame.Surface:
        return self._tiles[i]

class PPMap:
    def __init__(self, filename, tileset):
        with open(filename, "rb") as file_handle:
            self.raw_data = file_handle.read()

        self.width = (self.raw_data[0x17] << 8) + self.raw_data[0x18]
        self.height = (self.raw_data[0x19] << 8) + self.raw_data[0x1a]

        # self.tileset = TileSet()
        self.tileset = tileset

        self.map = self.unpack(self.raw_data[0x1b :])


        # for t in unpacked:
        #     print(hex(t), end=',')

    def run(self):


        display_size = (1600, 960)
        pygame.init()

        self.screen = pygame.display.set_mode(display_size)
        pygame.display.set_caption("Map Viewer")
        self.running = True

        width = self.width
        height = self.height
        # print(width)
        # sys.exit(0)


        position_x = 0
        position_y = 0

        padding = 0

        surface = pygame.Surface((32 * (width + 2), 32 * (height + 2)))


        while self.running:


            surface.fill((0, 0, 0))

            for j in range(height):
                for i in range(width):
                    tile_index = j * width + i - padding

                    if tile_index < 0:
                        tile_id = 0
                    else:
                        tile_id = self.map[tile_index]

                    # Drawing coords
                    x = (i + 1) * 32
                    y = (j + 1) * 32
                    effective_tile_id = tile_id & 0x3fff
                    surface.blit(self.tileset.get_tile(effective_tile_id), (x, y))

                    # if tile_id & 0x8000:
                    #     pygame.draw.rect(surface, (255, 0, 0), (x, y, x + 32, y + 32), width = 2)
                    #
                    # if tile_id & 0x4000:
                    #     pygame.draw.rect(surface, (0, 255, 0), (x, y, x + 32, y + 32), width = 1)

            self.screen.blit(surface, (position_x, position_y))
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == QUIT:
                    self.running = False

            key_input = pygame.key.get_pressed()
            if key_input[K_UP]:
                position_y += 32
            if key_input[K_DOWN]:
                position_y -= 32
            if key_input[K_LEFT]:
                position_x += 32
            if key_input[K_RIGHT]:
                position_x -= 32

        pygame.quit()

    @staticmethod
    def unpack(data):
        i = 0
        unpacked_map = []

        while i < len(data):
            current_byte = data[i]

            # repeat
            if current_byte & 0x80:
                repeat_count = current_byte - 0x80 + 1
                tile = (data[i + 1] << 8) + data[i + 2]
                unpacked_map += [tile] * repeat_count

                i += 3

            # next N + 1 tiles are is-is
            else:
                for j in range(current_byte + 1):
                    next_tile = (data[i + (j * 2) + 1] << 8) + data[i + (j * 2) + 2]
                    unpacked_map.append(next_tile)

                i += (j + 1) * 2 + 1

        return unpacked_map




if __name__ == "__main__":
    # map = PPMap("Jurassic.map-1")
    # map = PPMap("Power Pete/Data/Maps/Jurassic.map-1")
    # map.run()
    #
    image = PPImage("Power Pete/Data/Images/Titlepage.image")
    tileset = PPTileSet("Power Pete/Data/Maps/Candy.tileset", image.clut)
    map = PPMap("Power Pete/Data/Maps/Candy.Map-2", tileset)
    map.run()

    # with open("Power Pete/Data/Maps/Clown.tileset", "rb") as fh:
    #     with open("Clown.tileset.uncompressed", "wb") as wfh:
    #         wfh.write(Utils.unpack_generic(fh.read()))



    # image = PPImage("Power Pete/Data/Images/Titlepage.image")
    #
    # screen = pygame.display.set_mode((image.width, image.height))
    # pygame.display.set_caption("Image Viewer")
    # running = True
    #
    # screen.blit(image.image, (0, 0))
    #
    # pygame.display.update()
    #
    # while running:
    #     for event in pygame.event.get():
    #         if event.type == QUIT:
    #             running = False
    #
    # pygame.quit()



# file = 'tmw_desert_spacing.png'



#
# class Game:
#     W = 640
#     H = 240
#     SIZE = W, H
#
#     def __init__(self):
#         pygame.init()
#         self.screen = pygame.display.set_mode(Game.SIZE)
#         pygame.display.set_caption("Pygame Tiled Demo")
#         self.running = True
#
#     def run(self):
#         while self.running:
#             for event in pygame.event.get():
#                 if event.type == QUIT:
#                     self.running = False
#
#                 elif event.type == KEYDOWN:
#                     if event.key == K_l:
#                         self.load_image(file)
#
#         pygame.quit()
#
#     def load_image(self, file):
#         self.file = file
#         self.image = pygame.image.load(file)
#         self.rect = self.image.get_rect()
#
#         self.screen = pygame.display.set_mode(self.rect.size)
#         pygame.display.set_caption(f'size:{self.rect.size}')
#         self.screen.blit(self.image, self.rect)
#         pygame.display.update()
#
#
# game = Game()
# game.run()