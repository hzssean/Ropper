# coding=utf-8
#
# Copyright 2016 Sascha Schirra
#
# This file is part of Ropper.
#
# Ropper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ropper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import print_function
from ropper.common.utils import isHex, toHex
from ropper.common.coloredstring import cstr, Color
from ropper.common.error import RopperError
from ropper.loaders.loader import Loader
from ropper.ropchain.ropchain import RopChain
from ropper.arch import getArchitecture
from ropper.rop import Ropper, Format
from ropper.gadget import Gadget
from binascii import unhexlify
import re

def deleteDuplicates(gadgets, callback=None):
    toReturn = []
    inst = set()
    count = 0
    added = False
    for i,gadget in enumerate(gadgets):
        inst.add(gadget._gadget)
        if len(inst) > count:
            count = len(inst)
            toReturn.append(gadget)
            added = True
        if callback:
            callback(gadget, added, float(i)/(len(gadgets)-1))
            added = False
    return toReturn


def filterBadBytes(gadgets, badbytes):

    def formatBadBytes(badbytes):
        if len(badbytes) % 2 > 0:
            raise RopperError('The length of badbytes has to be a multiple of two')

        try:
            badbytes = unhexlify(badbytes)
        except:
            raise RopperError('Invalid characters in badbytes string')
        return badbytes


    if not badbytes:
        return gadgets

    

    badbytes = formatBadBytes(badbytes)
    if isinstance(gadgets, dict):
        toReturn = {}
        for file, gadget in gadgets.items():
            t = []
            for g in gadget:
                if not badbytes or not g.addressesContainsBytes(badbytes):
                    t.append(g)
            toReturn[file] = t
    elif isinstance(gadgets, list): 
        toReturn = []  
        for gadget in gadgets:
            if not badbytes or not gadget.addressesContainsBytes(badbytes):
                toReturn.append(gadget)

    return toReturn

class Options(object):

    def __init__(self, options={}, option_changed=None):
        super(Options, self).__init__()
        self.__checkOptions(options)
        self.__options_dict = options
        self.__option_changed = option_changed

    def __checkOptions(self, options):
        if not isinstance(options, dict):
            raise TypeError('options has to be an instance of dict')

        inst_count = options.get('inst_count')
        if inst_count and not isinstance(inst_count, (int)):
            raise TypeError('inst_count has to be an instance of int')
        elif not inst_count:
            options['inst_count'] = 6
        elif inst_count < 1:
            raise AttributeError('inst_count has to be bigger than 0')

        color = options.get('color')
        if color != None and not isinstance(color, bool):
            raise TypeError('color has to be an instance of bool')
        elif color == None:
            options['color'] = False

        badbytes = options.get('badbytes')
        if badbytes and not isinstance(badbytes, str):
            raise TypeError('color has to be an instance of bool')
        elif badbytes and len(badbytes) % 2 == 1:
            raise AttributeError('length of badbytes has to be even')
        elif badbytes and not isHex('0x'+badbytes):
            raise AttributeError('badbytes has to consist of 0-9 a-f A-F')
        elif not badbytes:
            options['badbytes'] = ''

        all = options.get('all')
        if all != None and not isinstance(all, bool):
            raise TypeError('color has to be an instance of bool')
        elif all == None:
            options['all'] = False

        gtype = options.get('type')
        if gtype and not isinstance(gtype, str):
            raise TypeError('type has to be an instance of str')
        elif gtype and gtype not in ['rop', 'jop', 'sys', 'all']:
            raise AttributeError('type has to be a "rop", "jop", "sys" or "all"')
        elif not gtype:
            options['type'] = 'all'

        detailed = options.get('detailed')
        if detailed != None and not isinstance(detailed, bool):
            raise TypeError('color has to be an instance of bool')
        elif detailed == None:
            options['detailed'] = False

    def items(self):
        for key, value in self.__options_dict.items():
            yield key, value

    def __getattr__(self, key):
        if key.startswith('_'):
            return super(Options, self).__getattr__(key)
        else:
            return self.__options_dict[key]

    def __setattr__(self, key, value):
        if key.startswith('_'):
            super(Options, self).__setattr__(key, value)
        else:
            old = self.__options_dict[key]
            self.__checkOptions({key:value})
            self.__options_dict[key] = value
            self.__checkOptions(self.__options_dict)
            if self.__option_changed:
                self.__option_changed(key, old, value)

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getitem__(self, key):
        return self.__getattr__(key)


class RopperService(object):

    def __init__(self, options={}, callbacks=None):
        super(RopperService, self).__init__()
        self.__options = Options(options, self.__optionChanged)
        if callbacks and hasattr(callbacks, '__gadgetSearchProgress__'):
            self.__ropper = Ropper(callback=callbacks.__gadgetSearchProgress__)
        else:
            self.__ropper = Ropper()
        self.__files = []
        self.__callbacks = callbacks
        if self.__options.color:
            cstr.COLOR = self.__options.color
        Gadget.DETAILED = self.__options.detailed

    @property
    def ropper(self):
        return self.__ropper
    
    @property
    def options(self):
        return self.__options

    @property
    def files(self):
        return list(self.__files)
    
    def __optionChanged(self, option, oldvalue, newvalue):
        if hasattr(self, '_%s_changed' % option):
            func = getattr(self, '_%s_changed' % option)
            func(newvalue)

    def __prepareGadgets(self, gadgets):

        gadgets = self.__filterBadBytes(gadgets)
        if not self.__options.all:
            callback = None
            if self.__callbacks and hasattr(self.__callbacks, '__deleteDoubleGadgetsProgress__'):
                callback = self.__callbacks.__deleteDoubleGadgetsProgress__
            gadgets = deleteDuplicates(gadgets, callback)
        return gadgets

    def __filterBadBytes(self, gadgets):
        if self.__options.badbytes:
            gadgets = filterBadBytes(gadgets, self.options.badbytes)
        return gadgets

    def _badbytes_changed(self, value):
        for f in self.__files:
            if f.loaded:
                f.gadgets = self.__prepareGadgets(f.allGadgets)

    def _all_changed(self, value):
        for f in self.__files:
            if f.loaded:
                f.gadgets = self.__prepareGadgets(f.allGadgets)

    def _color_changed(self, value):
        cstr.COLOR = value

    def _detailed_changed(self, value):
        Gadget.DETAILED = value

    def _getFileFor(self, name):
        for file in self.__files:
            if file.loader.fileName == name:
                return file

        return None

    def getFileFor(self, name):
        return self._getFileFor(name)
        
    def addFile(self, name, bytes=None, arch=None, raw=False):
        if self._getFileFor(name):
            raise RopperError('file is already added: %s' % name)

        if arch:
            arch=getArchitecture(arch)

        loader = Loader.open(name, bytes=bytes, raw=raw, arch=arch)
        if len(self.__files) > 0 and self.__files[0].loader.arch != loader.arch:
            raise RopperError('It is not supported to open file with different architectures! Loaded: %s; File to open: %s' % (str(self.__files[0].loader.arch), str(loader.arch)))
        file = FileContainer(loader)
        self.__files.append(file)

    def removeFile(self, name):
        for idx, fc in enumerate(self.__files):
            if fc.loader.fileName == name:
                del self.__files[idx]

    def asm(self, code, arch='x86', format='hex'):
        if format not in ('hex', 'string', 'raw'):
            raise RopperError('Invalid format: %s\n Valid formats are: hex, string, raw' % format)
        format = Format.HEX if format=='hex' else Format.STRING if format=='string' else Format.RAW
        return self.ropper.assemble(code, arch=getArchitecture(arch), format=format)

    def disasm(self, opcode, arch='x86'):
        return self.ropper.disassemble(opcode, arch=getArchitecture(arch))

    def searchPopPopRet(self, name=None):
        to_return = {}

        if not name:
            for file in self.__files:
                to_return[file.loader.fileName] = self.__ropper.searchPopPopRet(file.loader)
        else:
            fc = self._getFileFor(name)
            if not fc:
                raise RopperError('No such file opened: %s' % name)

            to_return[name] = self.__ropper.searchPopPopRet(fc.loader)

        return self.__filterBadBytes(to_return)

    def searchJmpReg(self, regs=['esp'],name=None):
        to_return = {}

        if not name:
            for file in self.__files:
                to_return[file.loader.fileName] = self.__ropper.searchJmpReg(file.loader, regs)
        else:
            fc = self._getFileFor(name)
            if not fc:
                raise RopperError('No such file opened: %s' % name)

            to_return[name] = self.__ropper.searchJmpReg(fc.loader, regs)

        return self.__filterBadBytes(to_return)

    def searchOpcode(self, opcode, name=None):
        to_return = {}

        if not name:
            for file in self.__files:
                to_return[file.loader.fileName] = self.__ropper.searchOpcode(file.loader, opcode)
        else:
            fc = self.getFileFor(name)
            if not fc:
                raise RopperError('No such file opened: %s' % name)

            to_return[name] = self.__ropper.searchOpcode(fc.loader, opcode)

        return self.__filterBadBytes(to_return)

    def searchInstructions(self, code, name=None):
        to_return = {}

        if not name:
            for file in self.__files:
                to_return[file.loader.fileName] = self.__ropper.searchInstructions(file.loader, code)
        else:
            fc = self.getFileFor(name)
            if not fc:
                raise RopperError('No such file opened: %s' % name)

            to_return[name] = self.__ropper.searchInstructions(fc.loader, code)

        return self.__filterBadBytes(to_return)

    def loadGadgetsFor(self, name=None):
        def load_gadgets(f):
            f.allGadgets = self.__ropper.searchGadgets(f.loader, instructionCount=self.options.inst_count)
            f.gadgets = self.__prepareGadgets(f.allGadgets)
         
        if name is None:
            for f in self.__files:
                load_gadgets(f)
        else:
            for f in self.__files:
                if f.loader.fileName == name:
                    load_gadgets(f)
                
    def printGadgetsFor(self, name=None):
        def print_gadgets(f):
            print(f.loader.fileName)
            for g in f.gadgets:
                if self.options.detailed:
                    print(g)
                else:
                    print(g.simpleString())

        if name is None:
            for f in self.__files:
                print_gadgets(f)
        else:
            for f in self.__files:
                if f.loader.fileName == name:
                    print_gadgets(f)

    def searchString(self, string='', name=None):

        def search(f, string):
            data = []
            if not string or string == '[ -~]{2}[ -~]*':
                string = '[ -~]{2}[ -~]*'
            else:
                string = f.arch.searcher.prepareFilter(string)
            sections = list(f.dataSections)
            string = string.encode('ascii') # python 3 compatibility
            for section in sections:
                b = bytes(bytearray(section.bytes))
                for match in re.finditer(string, b):
                    vaddr = f.imageBase + section.offset if f.imageBase != None else section.virtualAddress
                    data.append( (match.start() + vaddr , match.group()))
            return data

        to_return = {}
        if not name:
            for file in self.__files:
                to_return[file.loader.fileName] = search(file.loader, string)
        else:
            fc = self._getFileFor(name)
            if not fc:
                raise RopperError('No such file opened: %s' % name)
            to_return[name] = search(fc.loader, string)

        return to_return

    def search(self, search, quality=None, name=None):
        if name:
            fc = self._getFileFor(name)
            if not fc:
                raise RopperError('No such file opened: %s' % name)
            
            s = fc.loader.arch.searcher
            for gadget in s.search(fc.gadgets, search, quality):
                    yield(fc.name, gadget)
        else:        
            for fc in self.__files:
                s = fc.loader.arch.searcher
                for gadget in s.search(fc.gadgets, search, quality):
                    yield(fc.name, gadget)

    def searchdict(self, search, quality=None, name=None):
        to_return = {}
        for file, gadget in self.search(search, quality, name):
            l = to_return.get(file)
            if not l:
                l = []
                to_return[file] = l
            l.append(gadget)
        return to_return

    def disassAddress(self, name, address, length):
        fc = self.getFileFor(name)
        if not fc:
            raise RopperError('No such file opened: %s' % name)
        eSections = fc.loader.executableSections

        for section in  eSections:
            if section.virtualAddress <= address and section.virtualAddress + section.size > address:
                ropper = Ropper()


                g = ropper.disassembleAddress(section, fc.loader, address, address - (fc.loader.imageBase+section.offset), length)
                if not g:
                    raise RopperError('Cannot disassemble address: %s' % toHex(address))
                    
                if length < 0:
                    length = length * -1
                return g.disassemblyString()
        return ''
        
    def createRopChain(self, chain, options={}):
        callback = None
        if self.__callbacks and hasattr(self.__callbacks, '__ropchainMessages__'):
            callback = self.__callbacks.__ropchainMessages__

        b = []
        gadgets = {}
        for binary in self.__files:
            gadgets[binary.loader] = binary.gadgets
            b.append(binary.loader)
        generator = RopChain.get(b, gadgets, chain, callback, self.options.badbytes)

        if not generator:
            raise RopperError('%s does not have support for %s chain generation at the moment. Its a future feature.' % (self.files[0].loader.arch.__class__.__name__, chain))

        return generator.create(options)

    def setImageBaseFor(self, name, imagebase):
        file = self._getFileFor(name)
        if not file:
            raise RopperError('No such file opened: %s' % name)
        file.loader.imageBase = imagebase
        if file.loaded:
            file.gadgets = self.__prepareGadgets(file.allGadgets)

    def setArchitectureFor(self, name, arch):
        file = self.getFileFor(name)
        if not file:
            raise RopperError('No such file opened: %s' % name)
        file.loader.arch = getArchitecture(arch)
        file.allGadgets = None
        file.gadgets = None

    def _setGadgets(self, name, gadgets):
        fc = self.getFileFor(name)
        if not fc:
            raise RopperError('No such file opened: %s' % name)
        fc.allGadgets = gadgets
        fc.gadgets = self.__prepareGadgets(fc.allGadgets)



class FileContainer(object):

    def __init__(self, loader):
        super(FileContainer, self).__init__()

        self.__loader = loader
        self.__all_gadgets = None
        self.__gadgets = None
        self.__loaded = False

    @property
    def name(self):
        return self.loader.fileName
    
    @property
    def arch(self):
        return self.loader.arch

    @property
    def type(self):
        return self.loader.type
    
    @property
    def loaded(self):
        return self.__loaded

    @property
    def loader(self):
        return self.__loader
    
    @property
    def gadgets(self):
        return self.__gadgets

    @gadgets.setter
    def gadgets(self, gadgets):
        self.__gadgets = gadgets
    
    @property
    def allGadgets(self):
        return self.__all_gadgets

    @allGadgets.setter
    def allGadgets(self, gadgets):
        self.__loaded = True if gadgets is not None else False
        self.__all_gadgets = gadgets