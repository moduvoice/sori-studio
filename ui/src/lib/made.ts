// 이번 실행 동안 만든 소리(메모리에만 둬요). "소리 만들기"와 "홈"이 같이 써요.
export type Made = { id: number; engine: string; voice: string; text: string; blob: Blob; genS: number; audioS: number; retries: number; suspect: string };

export const recent: Made[] = []; // 화면을 옮겨 다녀도 이번 실행 동안은 남아요
const MAX = 5;

export function addMade(m: Made) {
  recent.unshift(m);
  recent.splice(MAX);
}

// 입력도 같이 남겨 "만든 소리" 와 어긋나지 않게(리뷰)
export const draft: { text: string | null } = { text: null };
