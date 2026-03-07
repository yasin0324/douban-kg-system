const STORAGE_KEY = "db-recommend-history:v1";
const HISTORY_TTL_MS = 30 * 60 * 1000;
const MAX_RECORDS_PER_ALGORITHM = 120;

const isClient = () => typeof window !== "undefined";

const pruneEntries = (entries = []) => {
    const now = Date.now();
    return entries.filter(
        (entry) =>
            entry &&
            entry.mid &&
            entry.ts &&
            now - Number(entry.ts) <= HISTORY_TTL_MS,
    );
};

const readHistory = () => {
    if (!isClient()) {
        return {};
    }
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (!raw) {
            return {};
        }
        const parsed = JSON.parse(raw);
        return typeof parsed === "object" && parsed ? parsed : {};
    } catch (error) {
        console.warn("读取推荐历史失败:", error);
        return {};
    }
};

const writeHistory = (history) => {
    if (!isClient()) {
        return;
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
};

export function useRecommendationHistory() {
    const getRecentMovieIds = (algorithm) => {
        const history = readHistory();
        const entries = pruneEntries(history[algorithm] || []);
        const deduped = [];
        const seen = new Set();
        entries
            .sort((a, b) => Number(b.ts) - Number(a.ts))
            .forEach((entry) => {
                if (seen.has(entry.mid)) {
                    return;
                }
                seen.add(entry.mid);
                deduped.push(entry.mid);
            });
        history[algorithm] = entries;
        writeHistory(history);
        return deduped;
    };

    const rememberMovies = (algorithm, movieIds = []) => {
        if (!algorithm || !movieIds.length) {
            return;
        }
        const history = readHistory();
        const now = Date.now();
        const nextEntries = pruneEntries([
            ...(history[algorithm] || []),
            ...movieIds
                .filter(Boolean)
                .map((mid) => ({ mid, ts: now })),
        ]).sort((a, b) => Number(b.ts) - Number(a.ts));
        history[algorithm] = nextEntries.slice(0, MAX_RECORDS_PER_ALGORITHM);
        writeHistory(history);
    };

    const buildRerollParams = (algorithm) => {
        const excludeMovieIds = getRecentMovieIds(algorithm);
        return {
            exclude_movie_ids: excludeMovieIds,
            reroll_token: `${algorithm}-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2, 8)}`,
        };
    };

    return {
        getRecentMovieIds,
        rememberMovies,
        buildRerollParams,
    };
}
