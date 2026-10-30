// test/hello.c
// Very simple C program we can try minimizing.

#include <stdio.h>

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
  struct S s = { 1, 2 };
  printf("%d\\n", helper(s.x, s.y));
  return 0;
}

// EOF
