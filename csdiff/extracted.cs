// VERBATIM extracts from WeaponCore 3.0. Only ProtoBuf attributes stripped and
// GetDeck's accessibility widened. No arithmetic altered.
using System;

namespace WcReal {
    public struct MyTuple<T1,T2> { public T1 Item1; public T2 Item2;
        public MyTuple(T1 a, T2 b){Item1=a;Item2=b;} }

    public struct XorShiftRandomStruct
        {
    
            // Constants
            private const double DoubleUnit = 1.0 / (int.MaxValue + 1.0);
    
            // State Fields
            private ulong _x;
            private ulong _y;
    
            // Buffer for optimized bit generation.
            private ulong _buffer;
            private ulong _bufferMask;
    
            /// <summary>
            ///   Constructs a new  generator
            ///   with the supplied seed.
            /// </summary>
            /// <param name="seed">
            ///   The seed value.
            /// </param>
            public XorShiftRandomStruct(ulong seed)
            {
                _x = seed << 3; _y = seed >> 3;
                _buffer = 0;
                _bufferMask = 0;
    
                var temp1 = _y; _x ^= _x << 23; var temp2 = _x ^ _y ^ (_x >> 17) ^ (_y >> 26); _x = temp1; _y = temp2;
                var tempX = _y; _x ^= _x << 23; var tempY = _x ^ _y ^ (_x >> 17) ^ (_y >> 26); var newSeed = tempY + _y; _x = tempX; _y = tempY;
                _x = newSeed << 3; _y = newSeed >> 3;
            }
    
            /// <summary>
            ///   Reinits existing Random class
            ///   with the supplied seed.
            /// </summary>
            /// <param name="seed">
            ///   The seed value.
            /// </param>
            public void Reinit(ulong seed)
            {
                _x = seed << 3; _y = seed >> 3;
                _buffer = 0;
                _bufferMask = 0;
    
                // 
                // random isn't very random unless we do the below.... likely because hashes produce incrementing numbers for Int3 conversions.
                //
    
                var temp1 = _y; _x ^= _x << 23; var temp2 = _x ^ _y ^ (_x >> 17) ^ (_y >> 26); _x = temp1; _y = temp2;
    
                var tempX = _y; _x ^= _x << 23; var tempY = _x ^ _y ^ (_x >> 17) ^ (_y >> 26); var newSeed = tempY + _y; _x = tempX; _y = tempY;
    
                _x = newSeed << 3; _y = newSeed >> 3;
            }
    
            public MyTuple<ulong, ulong> GetSeedVaues()
            {
                return new MyTuple<ulong, ulong>(_x, _y);
            }
    
            public void SyncSeed(ulong x, ulong y)
            {
                _x = x;
                _y = y;
            }
    
            /// <summary>
            ///   Generates a pseudorandom boolean.
            /// </summary>
            /// <returns>
            ///   A pseudorandom boolean.
            /// </returns>
            public bool NextBoolean()
            {
                if (_bufferMask > 0)
                {
                    var _ = (_buffer & _bufferMask) == 0;
                    _bufferMask >>= 1;
                    return _;
                }
    
                var tempX = _y;
                _x ^= _x << 23; var tempY = _x ^ _y ^ (_x >> 17) ^ (_y >> 26);
    
                _buffer = tempY + _y;
                _x = tempX;
                _y = tempY;
    
                _bufferMask = 0x8000000000000000;
                return (_buffer & 0xF000000000000000) == 0;
            }
    
            /// <summary>
            ///   Generates a pseudorandom 16-bit unsigned integer.
            /// </summary>
            /// <returns>
            ///   A pseudorandom 16-bit unsigned integer.
            /// </returns>
            public ushort NextUInt16()
            {
                var tempX = _y;
                _x ^= _x << 23; var tempY = _x ^ _y ^ (_x >> 17) ^ (_y >> 26);
    
                var _ = (ushort)(tempY + _y);
    
                _x = tempX;
                _y = tempY;
    
                return _;
            }
    
            /// <summary>
            ///   Generates a pseudorandom 64-bit unsigned integer.
            /// </summary>
            /// <returns>
            ///   A pseudorandom 64-bit unsigned integer.
            /// </returns>
            public ulong NextUInt64()
            {
                var tempX = _y;
                _x ^= _x << 23; var tempY = _x ^ _y ^ (_x >> 17) ^ (_y >> 26);
    
                var _ = tempY + _y;
    
                _x = tempX;
                _y = tempY;
    
                return _;
            }
    
            /// <summary>
            ///   Generates a pseudorandom double between
            ///   0 and 1 non-inclusive.
            /// </summary>
            /// <returns>
            ///   A pseudorandom double.
            /// </returns>
            public double NextDouble()
            {
                var tempX = _y;
                _x ^= _x << 23; var tempY = _x ^ _y ^ (_x >> 17) ^ (_y >> 26);
    
                var tempZ = tempY + _y;
                var _ = DoubleUnit * (0x7FFFFFFF & tempZ);
    
                _x = tempX;
                _y = tempY;
    
                return _;
            }
    
            public int Range(int aMin, int aMax)
            {
                var rndInt = (int)NextUInt64();
                var value = aMin + rndInt % (aMax - aMin);
    
                if (value < aMin || value > aMax)
                    value *= -1;
    
                return value;
            }
    
            public double Range(double aMin, double aMax)
            {
                var value = aMin + NextDouble() * (aMax - aMin);
                if (value < aMin || value > aMax)
                    value *= -1;
    
                return value;
            }
    
            public float Range(float aMin, float aMax)
            {
                var value = aMin + NextDouble() * (aMax - aMin);
                if (value < aMin || value > aMax)
                    value *= -1;
    
                return (float)value;
            }
    
            // corrects bit alignment which might shift the probability slightly to the
            // lower numbers based on the choosen range.
            public ulong FairRange(ulong aRange)
            {
                ulong dif = ulong.MaxValue % aRange;
                // if aligned or range too big, just pick a number
                if (dif == 0 || ulong.MaxValue / (aRange / 4UL) < 2UL)
                    return NextUInt64() % aRange;
                ulong v = NextUInt64();
                // avoid the last incomplete set
                while (ulong.MaxValue - v < dif)
                    v = NextUInt64();
                return v % aRange;
            }
        }

    public static class AiDeck {
        public static int[] GetDeck(ref int[] deck, int firstCard, int cardsToSort, int cardsToShuffle, ref XorShiftRandomStruct rng)
                {
                    if (deck.Length < cardsToSort)
                        deck = new int[cardsToSort * 2];
        
                    var shuffle = cardsToShuffle > 0;
        
                    var splitSize = shuffle && cardsToShuffle <= cardsToSort ? cardsToSort / cardsToShuffle : 0;
                    var startChunk = shuffle && splitSize > 0 ? rng.Range(1, splitSize + 1) : 0;
        
                    var end = (startChunk > 0 ? startChunk * cardsToShuffle : cardsToShuffle);
                    var start = (startChunk > 0 ? end - cardsToShuffle : 0) ;
                    for (int i = 0; i < cardsToSort; i++)
                    {
                        int j;
                        if (shuffle && i >= start && i < end)
                        {
                            j = rng.Range(0, i + 1);
                        }
                        else
                        {
                            j = i;
                        }
        
                        deck[i] = deck[j];
                        deck[j] = i + firstCard;
                    }
                    return deck;
                }
    }
}
