// test/hello-cpp.cc
// Very simple C++ program we can try minimizing.

#include <iostream>          // std::cout

struct S {
  int x;
  int y;
};

int helper(int a, int b)
{
  return a + b;
}

int main()
{
  S s = { 1, 2 };
  std::cout << helper(s.x, s.y) << "\n";
  return 0;
}

// EOF
