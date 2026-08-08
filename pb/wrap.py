"""Wrap a PB artifact in MyGridProgram so it can be compiled outside the game.

Usage: python wrap.py <path-to-artifact.cs>
Writes Wrapped.cs next to this script.
"""
import io
import os
import sys

HEAD = """using System;
using System.Collections.Generic;
using System.Text;
using System.Linq;
using Sandbox.ModAPI.Ingame;
using Sandbox.ModAPI.Interfaces;
using Sandbox.Game.EntityComponents;
using VRage;
using VRage.Game;
using VRage.Game.Components;
using VRage.Game.ModAPI.Ingame;
using VRage.Game.ObjectBuilders.Definitions;
using VRageMath;
using SpaceEngineers.Game.ModAPI.Ingame;

namespace PbCompileCheck {
public sealed class Program : MyGridProgram {
"""

src = io.open(sys.argv[1], encoding='utf-8').read()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Wrapped.cs')
io.open(out, 'w', encoding='utf-8').write(HEAD + src + '\n}\n}\n')
print('wrapped %s (%d chars)' % (os.path.basename(sys.argv[1]), len(src)))
