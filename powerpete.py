# import pygame
# from pygame.locals import *

# import sdl2
import ctypes
from typing import List

import numpy as np
import sdl2
import sdl2.ext

from sdl2 import SDL_CreateRGBSurface, SDL_GetError, Uint8, Uint32, SDL_Init, SDL_INIT_VIDEO, SDL_CreateWindow, \
    SDL_WINDOWPOS_CENTERED, SDL_GetWindowSurface, SDL_UpdateWindowSurface, SDL_BlitSurface, SDL_Event, SDL_PollEvent, \
    SDL_QUIT, SDL_Delay, SDL_DestroyWindow, SDL_Quit, SDL_LockSurface, SDL_UnlockSurface, SDL_WINDOW_SHOWN, SDL_Rect


# pygame.font.init()

class Color:
    #
    sdl_surface_bitmask = [
        0xff000000,
        0x00ff0000,
        0x0000ff00,
        0x000000ff
    ]

    # little endian
#     sdl_surface_bitmask = [
#         0x000000ff,
#         0x0000ff00,
#         0x00ff0000,
# #         0xff000000
#         0x0
#     ]

    def __init__(self, r, g, b, alpha):
        self.r = r
        self.g = g
        self.b = b
        self.alpha = alpha

    def __repr__(self):
        return f"{self.r} {self.g} {self.b} {self.alpha}"

    def to_sdl_bytes(self):
        return (self.r << 24) | (self.g << 16) | (self.b << 8) | self.alpha


class Utils:

    @staticmethod
    def create_surface(width, height):
        # RGBA
        surface = SDL_CreateRGBSurface(0, width, height, 32, *Color.sdl_surface_bitmask)
        # surface = SDL_CreateRGBSurface(0, width, height, 32, 0, 0, 0, 0)
        if surface is None:
            raise Exception(SDL_GetError())

        return surface

    # This should take a list and an offset instead of having the caller do that
    @staticmethod
    def read_short(data):
        return (data[0] << 8) + data[1]

    @staticmethod
    def read_short_2(data, offset):
        return (data[offset] << 8) + data[offset + 1]

    @staticmethod
    def read_long(data, offset):
        return (data[offset] << 24) | (data[offset + 1] << 16) | (data[offset + 2] << 8) | data[offset + 3]

    # Reads as tuples
    @staticmethod
    def read_clut(data):
        i = 0
        colors = []
        while i < len(data):
            colors.append((
                Utils.read_short_2(data, i) / 256.0,
                Utils.read_short_2(data, i + 2) / 256.0,
                Utils.read_short_2(data, i + 4) / 256.0))

            i += 6

        return colors

    # Returns list of color objects, ignore every other byte (assume that was a mistake in MM code..)
    @staticmethod
    def read_clut_2(data, offset):
        colors = []
        for i in range(256):
            r = data[offset]
            g = data[offset + 2]
            b = data[offset + 4]
            colors.append(Color(r, g, b, 0xff))
            offset += 6

        return colors

    @staticmethod
    def read_image(data, offset, width, height, clut: List[Color]):

        surface = Utils.create_surface(width, height)

        # if (SDL_LockSurface(surface) != 0):
        #     raise Exception(SDL_GetError())

        pixel_buffer = ctypes.cast(surface.contents.pixels, ctypes.POINTER(ctypes.c_uint))
        # pixel_buffer = ctypes.cast(surface.contents.pixels, ctypes.POINTER(ctypes.c_byte))

        for y in range(height):
            for x in range(width):
                pixel_buffer[((y * width) + x)] = clut[data[offset]].to_sdl_bytes()
                offset += 1

        # SDL_UnlockSurface(surface)

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
    def read_tile_flag_list(data, offset):
        count = Utils.read_short_2(data, offset)
        offset += 2

        tile_flags = []
        for i in range(count):
            current_flags = []
            current_flags.append(Utils.read_long(data, offset))
            current_flags.append(Utils.read_long(data, offset + 4))
            print(str(i) + ": " + hex(current_flags[0]) + ", " + hex(current_flags[1]))
            tile_flags.append(current_flags)
            offset += 8

        return tile_flags, offset


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

        with open(filename, "rb") as file_handle:
            raw_data = Utils.unpack_generic(file_handle.read())

        self.clut = Utils.read_clut_2(raw_data, 0x08)
        self.width = Utils.read_short_2(raw_data, 0x608)
        self.height = Utils.read_short_2(raw_data, 0x60a)

        self.surface = Utils.read_image(raw_data, 0x60c, self.width, self.height, self.clut)


class PPTileSet:
    def __init__(self, filename, clut):

        with open(filename, "rb") as file_handle:
            self.raw_data = Utils.unpack_generic(file_handle.read())

        filename_count = Utils.read_short_2(self.raw_data, 0x26)

        tile_count_offset = 0x28 + (filename_count * 0x100)

        tile_count = Utils.read_short_2(self.raw_data, tile_count_offset)
        self.tiles = []

        offset = tile_count_offset + 2
        for i in range(tile_count):
            self.tiles.append(Utils.read_image(self.raw_data, offset + (i * (32 * 32)), 32, 32, clut))

        offset += tile_count * 32 * 32

        self.tile_index_list, offset = Utils.read_tile_index_list(self.raw_data, offset)
        self.tile_flag_list, offset = Utils.read_tile_flag_list(self.raw_data, offset)

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

    # @staticmethod
    # def read_tile(data):
    #     if len(data) != 32 * 32:
    #         raise Exception("Invalid tile length")
    #
    #     i = 0
    #     surface = pygame.Surface((32, 32))
    #     pixel_array = pygame.PixelArray(surface)
    #
    #     for y in range(32):
    #         for x in range(32):
    #             current_byte = data[i]
    #             color = (current_byte, current_byte, current_byte)
    #             pixel_array[x, y] = color
    #             i += 1
    #
    #     pixel_array.close()
    #
    #     return surface


class PPMap:
    def __init__(self, filename, tileset):
        with open(filename, "rb") as file_handle:
            self.raw_data = file_handle.read()

        # self.width = (self.raw_data[0x17] << 8) + self.raw_data[0x18]
        self.width = Utils.read_short_2(self.raw_data, 0x17)
        # self.height = (self.raw_data[0x19] << 8) + self.raw_data[0x1a]
        self.height = Utils.read_short_2(self.raw_data, 0x19)

        self.tileset = tileset

        self.map = self.unpack(self.raw_data[0x1b :])

    def run(self):


        display_size = (1600, 960)
        # pygame.init()
        #
        # self.screen = pygame.display.set_mode(display_size)
        # pygame.display.set_caption("Map Viewer")
        window = SDL_CreateWindow(b"Map Viewer", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, display_size[0], display_size[1],
                                  SDL_WINDOW_SHOWN)
        screen_surface = SDL_GetWindowSurface(window)

        running = True

        width = self.width
        height = self.height

        position_x = 0
        position_y = 0

        padding = 0

        # surface = pygame.Surface((32 * (width + 2), 32 * (height + 2)))
        map_surface = Utils.create_surface(32 * (width + 2), 32 * (height + 2))

        copy_from_rect = SDL_Rect(0, 0, display_size[0], display_size[1])

        # surface.fill((0, 0, 0))

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
                # surface.blit(self.tileset.get_tile(effective_tile_id), (x, y))
                SDL_BlitSurface(
                    self.tileset.get_tile(effective_tile_id),
                    None,
                    map_surface,
                    SDL_Rect(x, y, 32, 32),
                )

                tile_flags_0 = self.tileset.tile_flag_list[effective_tile_id][0]
                # if tile_flags_0 & 0x2000000:
                #     sdl2.SDL_FillRect(map_surface, SDL_Rect(x, y, 3, 3), 0xff0000ff)
                # if tile_flags_0 & 0x4000000:
                #     sdl2.SDL_FillRect(map_surface, SDL_Rect(x + 3, y, 3, 3), 0xff00ffff)
                # if tile_flags_0 & 0x8000000:
                #     # yellow
                #     sdl2.SDL_FillRect(map_surface, SDL_Rect(x + 6, y, 3, 3), 0xffff00ff)

                # "Block is solid?"
                if tile_flags_0 & 0xf0000:
                    # blue
                    color = 0xffff00ff
                    sdl2.SDL_FillRect(map_surface, SDL_Rect(x , y, 2, 32), color)
                    sdl2.SDL_FillRect(map_surface, SDL_Rect(x, y, 32, 2), color)

        while running:
            copy_from_rect.x = position_x
            copy_from_rect.y = position_y

            if SDL_BlitSurface(map_surface, copy_from_rect, screen_surface, None) != 0:
                print(SDL_GetError())

            if SDL_UpdateWindowSurface(window) != 0:
                print(SDL_GetError())

            # event = SDL_Event()
            # while SDL_PollEvent(ctypes.byref(event)) != 0:
            #     if event.type == SDL_QUIT:
            #         running = False
            #         break

            for event in sdl2.ext.get_events():
                if event.type == sdl2.SDL_QUIT:
                    running = False
                    break

            key_states = sdl2.SDL_GetKeyboardState(None)
            if key_states[sdl2.SDL_SCANCODE_UP]:
                position_y -= 32
            if key_states[sdl2.SDL_SCANCODE_DOWN]:
                position_y += 32
            if key_states[sdl2.SDL_SCANCODE_LEFT]:
                position_x -= 32
            if key_states[sdl2.SDL_SCANCODE_RIGHT]:
                position_x += 32
            # SDL_Delay(10)

        SDL_DestroyWindow(window)
        SDL_Quit()


            # pygame.display.flip()

        #     for event in pygame.event.get():
        #         if event.type == QUIT:
        #             self.running = False
        #
        #     key_input = pygame.key.get_pressed()
        #     if key_input[K_UP]:
        #         position_y += 32
        #     if key_input[K_DOWN]:
        #         position_y -= 32
        #     if key_input[K_LEFT]:
        #         position_x += 32
        #     if key_input[K_RIGHT]:
        #         position_x -= 32
        #
        # pygame.quit()

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



def image_viewer_test():
    SDL_Init(SDL_INIT_VIDEO)

    image = PPImage("../Power Pete/Data/Images/Titlepage.image")

    window = SDL_CreateWindow(b"poop", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, image.width, image.height,
                              SDL_WINDOW_SHOWN)
    surface = SDL_GetWindowSurface(window)

    if SDL_BlitSurface(image.surface, None, surface, None) != 0:
        print(SDL_GetError())

    if SDL_UpdateWindowSurface(window) != 0:
        print(SDL_GetError())

    running = True
    event = SDL_Event()
    while running:
        while SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == SDL_QUIT:
                running = False
                break
        SDL_Delay(10)

    SDL_DestroyWindow(window)
    SDL_Quit()


if __name__ == "__main__":
    # map = PPMap("Jurassic.map-1")
    # map = PPMap("Power Pete/Data/Maps/Jurassic.map-1")
    # map.run()
    #


    image = PPImage("../Power Pete/Data/Images/Titlepage.image")
    tileset = PPTileSet("../Power Pete/Data/Maps/Jurassic.Tileset", image.clut)
    map = PPMap("../Power Pete/Data/Maps/Jurassic.map-3", tileset)
    map.run()

    # with open("Power Pete/Data/Maps/Clown.tileset", "rb") as fh:
    #     with open("Clown.tileset.uncompressed", "wb") as wfh:
    #         wfh.write(Utils.unpack_generic(fh.read()))





