#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace autotessell::matching {

// First-party Edmonds/Galil primal-dual maximum-weight matching.
//
// The implementation uses exact integer reduced costs.  Contracted odd cycles
// occupy indices above the original vertex range.  Runtime is O(V^3), memory
// is O(V^2).  It intentionally exposes only the mate vector needed by the
// report-only polyhedral face-pairing metric.
class MaximumWeightMatching final {
public:
    using Weight = std::int64_t;

    explicit MaximumWeightMatching(int vertex_count)
        : vertex_count_(vertex_count),
          active_count_(vertex_count),
          capacity_(2 * vertex_count + 1),
          edge_(static_cast<std::size_t>(capacity_),
                std::vector<Edge>(static_cast<std::size_t>(capacity_))),
          dual_(static_cast<std::size_t>(capacity_), 0),
          mate_(static_cast<std::size_t>(capacity_), 0),
          slack_from_(static_cast<std::size_t>(capacity_), 0),
          base_(static_cast<std::size_t>(capacity_), 0),
          parent_(static_cast<std::size_t>(capacity_), 0),
          forest_label_(static_cast<std::size_t>(capacity_), kUnseen),
          seen_at_(static_cast<std::size_t>(capacity_), 0),
          cycle_(static_cast<std::size_t>(capacity_)),
          immediate_child_(static_cast<std::size_t>(capacity_),
                           std::vector<int>(static_cast<std::size_t>(capacity_), 0))
    {
        if (vertex_count_ < 0) {
            throw std::invalid_argument("vertex count must be non-negative");
        }
        for (int vertex = 1; vertex <= vertex_count_; ++vertex) {
            base_[static_cast<std::size_t>(vertex)] = vertex;
            immediate_child_[static_cast<std::size_t>(vertex)]
                            [static_cast<std::size_t>(vertex)] = vertex;
        }
    }

    void add_edge(int first, int second, Weight weight)
    {
        validate_original_vertex(first);
        validate_original_vertex(second);
        if (first == second) {
            throw std::invalid_argument("matching graph cannot contain self edges");
        }
        if (weight <= 0) {
            throw std::invalid_argument("matching edge weights must be positive");
        }
        edge_at(first, second) = Edge{first, second, weight};
        edge_at(second, first) = Edge{second, first, weight};
    }

    [[nodiscard]] std::vector<int> solve()
    {
        if (vertex_count_ == 0) {
            return {};
        }
        Weight maximum_weight = 0;
        for (int first = 1; first <= vertex_count_; ++first) {
            for (int second = first + 1; second <= vertex_count_; ++second) {
                maximum_weight = std::max(maximum_weight, edge_at(first, second).weight);
            }
        }
        if (vertex_count_ > 1 && maximum_weight <= 0) {
            throw std::invalid_argument("matching graph must be complete");
        }
        for (int vertex = 1; vertex <= vertex_count_; ++vertex) {
            dual_[static_cast<std::size_t>(vertex)] = maximum_weight;
        }
        while (augment_once()) {
        }

        std::vector<int> result(static_cast<std::size_t>(vertex_count_), -1);
        for (int vertex = 1; vertex <= vertex_count_; ++vertex) {
            const int matched = mate_[static_cast<std::size_t>(vertex)];
            if (matched > 0 && matched <= vertex_count_) {
                result[static_cast<std::size_t>(vertex - 1)] = matched - 1;
            }
        }
        return result;
    }

private:
    struct Edge final {
        int from = 0;
        int to = 0;
        Weight weight = 0;
    };

    static constexpr int kUnseen = -1;
    static constexpr int kOuter = 0;
    static constexpr int kInner = 1;
    static constexpr Weight kInfinity = std::numeric_limits<Weight>::max() / 4;

    int vertex_count_;
    int active_count_;
    int capacity_;
    int timestamp_ = 0;
    std::vector<std::vector<Edge>> edge_;
    std::vector<Weight> dual_;
    std::vector<int> mate_;
    std::vector<int> slack_from_;
    std::vector<int> base_;
    std::vector<int> parent_;
    std::vector<int> forest_label_;
    std::vector<int> seen_at_;
    std::vector<std::vector<int>> cycle_;
    std::vector<std::vector<int>> immediate_child_;
    std::queue<int> queue_;

    [[nodiscard]] Edge& edge_at(int first, int second)
    {
        return edge_[static_cast<std::size_t>(first)][static_cast<std::size_t>(second)];
    }

    [[nodiscard]] const Edge& edge_at(int first, int second) const
    {
        return edge_[static_cast<std::size_t>(first)][static_cast<std::size_t>(second)];
    }

    void validate_original_vertex(int vertex) const
    {
        if (vertex < 1 || vertex > vertex_count_) {
            throw std::out_of_range("matching vertex index out of range");
        }
    }

    [[nodiscard]] Weight reduced_cost(const Edge& edge) const
    {
        return dual_[static_cast<std::size_t>(edge.from)]
            + dual_[static_cast<std::size_t>(edge.to)] - 2 * edge.weight;
    }

    void update_slack(int outer_vertex, int target_base)
    {
        const int current = slack_from_[static_cast<std::size_t>(target_base)];
        if (current == 0
            || reduced_cost(edge_at(outer_vertex, target_base))
                   < reduced_cost(edge_at(current, target_base))) {
            slack_from_[static_cast<std::size_t>(target_base)] = outer_vertex;
        }
    }

    void recompute_slack(int target_base)
    {
        slack_from_[static_cast<std::size_t>(target_base)] = 0;
        for (int candidate = 1; candidate <= active_count_; ++candidate) {
            if (edge_at(candidate, target_base).weight > 0
                && base_[static_cast<std::size_t>(candidate)] != target_base
                && forest_label_[static_cast<std::size_t>(
                       base_[static_cast<std::size_t>(candidate)])] == kOuter) {
                update_slack(candidate, target_base);
            }
        }
    }

    void enqueue_original_vertices(int vertex_or_cycle)
    {
        if (vertex_or_cycle <= vertex_count_) {
            queue_.push(vertex_or_cycle);
            return;
        }
        for (const int child : cycle_[static_cast<std::size_t>(vertex_or_cycle)]) {
            enqueue_original_vertices(child);
        }
    }

    void assign_base(int vertex_or_cycle, int new_base)
    {
        base_[static_cast<std::size_t>(vertex_or_cycle)] = new_base;
        if (vertex_or_cycle <= vertex_count_) {
            return;
        }
        for (const int child : cycle_[static_cast<std::size_t>(vertex_or_cycle)]) {
            assign_base(child, new_base);
        }
    }

    [[nodiscard]] int rotate_cycle_to_even_entry(int blossom, int child)
    {
        auto& members = cycle_[static_cast<std::size_t>(blossom)];
        const auto found = std::find(members.begin(), members.end(), child);
        if (found == members.end()) {
            throw std::logic_error("blossom entry child not found");
        }
        int position = static_cast<int>(std::distance(members.begin(), found));
        if ((position & 1) != 0) {
            std::reverse(members.begin() + 1, members.end());
            position = static_cast<int>(members.size()) - position;
        }
        return position;
    }

    void assign_match(int vertex_or_cycle, int partner)
    {
        mate_[static_cast<std::size_t>(vertex_or_cycle)] = edge_at(vertex_or_cycle, partner).to;
        if (vertex_or_cycle <= vertex_count_) {
            return;
        }

        const Edge entry_edge = edge_at(vertex_or_cycle, partner);
        const int entry_child = immediate_child_[static_cast<std::size_t>(vertex_or_cycle)]
                                                [static_cast<std::size_t>(entry_edge.from)];
        const int entry_position = rotate_cycle_to_even_entry(vertex_or_cycle, entry_child);
        auto& members = cycle_[static_cast<std::size_t>(vertex_or_cycle)];
        for (int index = 0; index < entry_position; ++index) {
            assign_match(members[static_cast<std::size_t>(index)],
                         members[static_cast<std::size_t>(index ^ 1)]);
        }
        assign_match(entry_child, partner);
        std::rotate(members.begin(),
                    members.begin() + entry_position,
                    members.end());
    }

    void augment_path(int outer_base, int other_outer_base)
    {
        while (true) {
            const int previous_matched_base =
                base_[static_cast<std::size_t>(mate_[static_cast<std::size_t>(outer_base)])];
            assign_match(outer_base, other_outer_base);
            if (previous_matched_base == 0) {
                return;
            }
            const int parent_base =
                base_[static_cast<std::size_t>(parent_[static_cast<std::size_t>(previous_matched_base)])];
            assign_match(previous_matched_base, parent_base);
            outer_base = parent_base;
            other_outer_base = previous_matched_base;
        }
    }

    [[nodiscard]] int lowest_common_outer_base(int first, int second)
    {
        ++timestamp_;
        while (first != 0 || second != 0) {
            if (first != 0) {
                if (seen_at_[static_cast<std::size_t>(first)] == timestamp_) {
                    return first;
                }
                seen_at_[static_cast<std::size_t>(first)] = timestamp_;
                first = base_[static_cast<std::size_t>(mate_[static_cast<std::size_t>(first)])];
                if (first != 0) {
                    first = base_[static_cast<std::size_t>(parent_[static_cast<std::size_t>(first)])];
                }
            }
            std::swap(first, second);
        }
        return 0;
    }

    [[nodiscard]] int allocate_blossom()
    {
        int blossom = vertex_count_ + 1;
        while (blossom <= active_count_
               && base_[static_cast<std::size_t>(blossom)] != 0) {
            ++blossom;
        }
        if (blossom > active_count_) {
            ++active_count_;
            blossom = active_count_;
        }
        if (blossom >= capacity_) {
            throw std::logic_error("weighted matching blossom capacity exceeded");
        }
        return blossom;
    }

    void append_tree_path(std::vector<int>& members, int start, int root)
    {
        for (int current = start; current != root;) {
            members.push_back(current);
            const int matched_base =
                base_[static_cast<std::size_t>(mate_[static_cast<std::size_t>(current)])];
            members.push_back(matched_base);
            enqueue_original_vertices(matched_base);
            current = base_[static_cast<std::size_t>(parent_[static_cast<std::size_t>(matched_base)])];
        }
    }

    void contract_blossom(int first_outer, int common_base, int second_outer)
    {
        const int blossom = allocate_blossom();
        dual_[static_cast<std::size_t>(blossom)] = 0;
        forest_label_[static_cast<std::size_t>(blossom)] = kOuter;
        mate_[static_cast<std::size_t>(blossom)] =
            mate_[static_cast<std::size_t>(common_base)];

        auto& members = cycle_[static_cast<std::size_t>(blossom)];
        members.clear();
        members.push_back(common_base);
        append_tree_path(members, first_outer, common_base);
        std::reverse(members.begin() + 1, members.end());
        append_tree_path(members, second_outer, common_base);

        assign_base(blossom, blossom);
        std::fill(immediate_child_[static_cast<std::size_t>(blossom)].begin(),
                  immediate_child_[static_cast<std::size_t>(blossom)].end(), 0);
        for (int candidate = 1; candidate <= active_count_; ++candidate) {
            edge_at(blossom, candidate) = Edge{};
            edge_at(candidate, blossom) = Edge{};
        }

        for (const int child : members) {
            for (int candidate = 1; candidate <= active_count_; ++candidate) {
                const Edge& candidate_edge = edge_at(child, candidate);
                if (candidate_edge.weight <= 0) {
                    continue;
                }
                Edge& current = edge_at(blossom, candidate);
                if (current.weight == 0
                    || reduced_cost(candidate_edge) < reduced_cost(current)) {
                    current = candidate_edge;
                    edge_at(candidate, blossom) = edge_at(candidate, child);
                }
            }
            for (int original = 1; original <= vertex_count_; ++original) {
                if (immediate_child_[static_cast<std::size_t>(child)]
                                    [static_cast<std::size_t>(original)] != 0) {
                    immediate_child_[static_cast<std::size_t>(blossom)]
                                    [static_cast<std::size_t>(original)] = child;
                }
            }
        }
        recompute_slack(blossom);
    }

    void expand_blossom(int blossom)
    {
        for (const int child : cycle_[static_cast<std::size_t>(blossom)]) {
            assign_base(child, child);
        }
        const int parent_vertex = parent_[static_cast<std::size_t>(blossom)];
        const Edge& parent_edge = edge_at(blossom, parent_vertex);
        const int entry_child = immediate_child_[static_cast<std::size_t>(blossom)]
                                                [static_cast<std::size_t>(parent_edge.from)];
        const int entry_position = rotate_cycle_to_even_entry(blossom, entry_child);
        auto& members = cycle_[static_cast<std::size_t>(blossom)];

        for (int index = 0; index < entry_position; index += 2) {
            const int outer_child = members[static_cast<std::size_t>(index)];
            const int inner_child = members[static_cast<std::size_t>(index + 1)];
            parent_[static_cast<std::size_t>(outer_child)] =
                edge_at(inner_child, outer_child).from;
            forest_label_[static_cast<std::size_t>(outer_child)] = kInner;
            forest_label_[static_cast<std::size_t>(inner_child)] = kOuter;
            slack_from_[static_cast<std::size_t>(outer_child)] = 0;
            recompute_slack(inner_child);
            enqueue_original_vertices(inner_child);
        }
        forest_label_[static_cast<std::size_t>(entry_child)] = kInner;
        parent_[static_cast<std::size_t>(entry_child)] = parent_vertex;
        for (std::size_t index = static_cast<std::size_t>(entry_position + 1);
             index < members.size(); ++index) {
            const int child = members[index];
            forest_label_[static_cast<std::size_t>(child)] = kUnseen;
            recompute_slack(child);
        }
        base_[static_cast<std::size_t>(blossom)] = 0;
    }

    [[nodiscard]] bool process_tight_edge(const Edge& tight_edge)
    {
        const int first_base = base_[static_cast<std::size_t>(tight_edge.from)];
        const int second_base = base_[static_cast<std::size_t>(tight_edge.to)];
        if (forest_label_[static_cast<std::size_t>(second_base)] == kUnseen) {
            parent_[static_cast<std::size_t>(second_base)] = tight_edge.from;
            forest_label_[static_cast<std::size_t>(second_base)] = kInner;
            const int matched_base =
                base_[static_cast<std::size_t>(mate_[static_cast<std::size_t>(second_base)])];
            slack_from_[static_cast<std::size_t>(second_base)] = 0;
            slack_from_[static_cast<std::size_t>(matched_base)] = 0;
            forest_label_[static_cast<std::size_t>(matched_base)] = kOuter;
            enqueue_original_vertices(matched_base);
            return false;
        }
        if (forest_label_[static_cast<std::size_t>(second_base)] != kOuter) {
            return false;
        }
        const int common_base = lowest_common_outer_base(first_base, second_base);
        if (common_base == 0) {
            augment_path(first_base, second_base);
            augment_path(second_base, first_base);
            return true;
        }
        contract_blossom(first_base, common_base, second_base);
        return false;
    }

    void initialize_search_forest()
    {
        std::fill(forest_label_.begin(), forest_label_.end(), kUnseen);
        std::fill(slack_from_.begin(), slack_from_.end(), 0);
        queue_ = std::queue<int>{};
        for (int vertex = 1; vertex <= active_count_; ++vertex) {
            if (base_[static_cast<std::size_t>(vertex)] == vertex
                && mate_[static_cast<std::size_t>(vertex)] == 0) {
                parent_[static_cast<std::size_t>(vertex)] = 0;
                forest_label_[static_cast<std::size_t>(vertex)] = kOuter;
                enqueue_original_vertices(vertex);
            }
        }
    }

    [[nodiscard]] Weight next_dual_step() const
    {
        Weight step = kInfinity;
        for (int blossom = vertex_count_ + 1; blossom <= active_count_; ++blossom) {
            if (base_[static_cast<std::size_t>(blossom)] == blossom
                && forest_label_[static_cast<std::size_t>(blossom)] == kInner) {
                step = std::min(step, dual_[static_cast<std::size_t>(blossom)] / 2);
            }
        }
        for (int target = 1; target <= active_count_; ++target) {
            if (base_[static_cast<std::size_t>(target)] != target) {
                continue;
            }
            const int slack_source = slack_from_[static_cast<std::size_t>(target)];
            if (slack_source == 0) {
                continue;
            }
            const Weight cost = reduced_cost(edge_at(slack_source, target));
            if (forest_label_[static_cast<std::size_t>(target)] == kUnseen) {
                step = std::min(step, cost);
            } else if (forest_label_[static_cast<std::size_t>(target)] == kOuter) {
                step = std::min(step, cost / 2);
            }
        }
        return step;
    }

    void apply_dual_step(Weight step)
    {
        for (int vertex = 1; vertex <= vertex_count_; ++vertex) {
            const int vertex_base = base_[static_cast<std::size_t>(vertex)];
            if (forest_label_[static_cast<std::size_t>(vertex_base)] == kOuter) {
                dual_[static_cast<std::size_t>(vertex)] -= step;
            } else if (forest_label_[static_cast<std::size_t>(vertex_base)] == kInner) {
                dual_[static_cast<std::size_t>(vertex)] += step;
            }
        }
        for (int blossom = vertex_count_ + 1; blossom <= active_count_; ++blossom) {
            if (base_[static_cast<std::size_t>(blossom)] != blossom) {
                continue;
            }
            if (forest_label_[static_cast<std::size_t>(blossom)] == kOuter) {
                dual_[static_cast<std::size_t>(blossom)] += 2 * step;
            } else if (forest_label_[static_cast<std::size_t>(blossom)] == kInner) {
                dual_[static_cast<std::size_t>(blossom)] -= 2 * step;
            }
        }
    }

    [[nodiscard]] bool process_new_tight_slacks()
    {
        queue_ = std::queue<int>{};
        for (int target = 1; target <= active_count_; ++target) {
            if (base_[static_cast<std::size_t>(target)] != target) {
                continue;
            }
            const int source = slack_from_[static_cast<std::size_t>(target)];
            if (source != 0 && base_[static_cast<std::size_t>(source)] != target
                && reduced_cost(edge_at(source, target)) == 0
                && process_tight_edge(edge_at(source, target))) {
                return true;
            }
        }
        return false;
    }

    void expand_zero_dual_inner_blossoms()
    {
        for (int blossom = vertex_count_ + 1; blossom <= active_count_; ++blossom) {
            if (base_[static_cast<std::size_t>(blossom)] == blossom
                && forest_label_[static_cast<std::size_t>(blossom)] == kInner
                && dual_[static_cast<std::size_t>(blossom)] == 0) {
                expand_blossom(blossom);
            }
        }
    }

    [[nodiscard]] bool augment_once()
    {
        initialize_search_forest();
        if (queue_.empty()) {
            return false;
        }
        while (true) {
            while (!queue_.empty()) {
                const int original = queue_.front();
                queue_.pop();
                if (forest_label_[static_cast<std::size_t>(
                        base_[static_cast<std::size_t>(original)])] == kInner) {
                    continue;
                }
                for (int other = 1; other <= vertex_count_; ++other) {
                    const Edge& candidate = edge_at(original, other);
                    if (candidate.weight <= 0
                        || base_[static_cast<std::size_t>(original)]
                               == base_[static_cast<std::size_t>(other)]) {
                        continue;
                    }
                    if (reduced_cost(candidate) == 0) {
                        if (process_tight_edge(candidate)) {
                            return true;
                        }
                    } else {
                        update_slack(original, base_[static_cast<std::size_t>(other)]);
                    }
                }
            }

            const Weight step = next_dual_step();
            if (step == kInfinity) {
                return false;
            }
            if (step < 0) {
                throw std::logic_error("weighted matching negative dual step");
            }
            apply_dual_step(step);
            if (process_new_tight_slacks()) {
                return true;
            }
            expand_zero_dual_inner_blossoms();
        }
    }
};

}  // namespace autotessell::matching
