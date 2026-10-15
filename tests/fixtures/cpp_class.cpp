// Test fixture — C++ class with methods, qualified names, and templates.
// Exercises C++ support (PRD task 2.3).

#include <string>
#include <vector>

namespace geo {

class Point {
public:
    Point(double x, double y) : x_(x), y_(y) {}

    double getX() const { return x_; }
    double getY() const { return y_; }

    double distanceTo(const Point& other) const;

private:
    double x_;
    double y_;
};

double Point::distanceTo(const Point& other) const {
    double dx = x_ - other.x_;
    double dy = y_ - other.y_;
    return dx * dx + dy * dy;
}

struct BoundingBox {
    Point min_corner;
    Point max_corner;

    bool contains(const Point& p) const {
        return p.getX() >= min_corner.getX()
            && p.getX() <= max_corner.getX()
            && p.getY() >= min_corner.getY()
            && p.getY() <= max_corner.getY();
    }
};

enum class Color {
    Red,
    Green,
    Blue,
};

typedef std::vector<Point> PointList;

static int helper_count = 0;

static void increment_count() {
    helper_count++;
}

} // namespace geo
