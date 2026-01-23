#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>

int main(int argc, char* argv[]) {

    std::vector<int> vec;
    vec.push_back(1);
    vec.push_back(2);

    for (auto& x : vec) {
        std::cout << x << "\n";
    }
    return 0;
}
