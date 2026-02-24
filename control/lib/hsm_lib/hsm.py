"""
hsm.py
Hierarchical State Machine (HSM) library cho Python
Version: 2.0.0 (port từ C)
"""

from typing import Callable, Any, Optional
from enum import IntEnum

from hsm_config import MAX_DEPTH, HISTORY


class HsmEvent(IntEnum):
    """Các event chuẩn của HSM"""
    NONE = 0x00
    ENTRY = 0x01
    EXIT = 0x02
    USER = 0x10         # User events bắt đầu từ đây


class HsmResult(IntEnum):
    """Kết quả trả về của các hàm HSM"""
    OK = 0
    ERROR = 1
    INVALID_PARAM = 2
    MAX_DEPTH = 3


class HsmState:
    """Định nghĩa một trạng thái trong HSM"""

    def __init__(
        self,
        name: str,
        handler: Callable[['Hsm', int, Any], int],
        parent: Optional['HsmState'] = None
    ):
        self.name = name
        self.handler = handler
        self.parent = parent


class Hsm:
    """Instance của Hierarchical State Machine"""

    def __init__(self, name: str = "HSM"):
        self.name = name
        self.current: Optional[HsmState] = None
        self.initial: Optional[HsmState] = None
        self.next: Optional[HsmState] = None           # deferred transition
        self.depth: int = 0
        self.in_transition: bool = False

        if HISTORY:
            self.history: Optional[HsmState] = None

    def init(self, initial_state: HsmState) -> HsmResult:
        """Khởi tạo HSM với trạng thái ban đầu"""
        if initial_state is None:
            return HsmResult.INVALID_PARAM

        self.initial = initial_state
        self.current = initial_state
        self.next = None
        self.depth = self._get_state_depth(initial_state)
        self.in_transition = False

        if HISTORY:
            self.history = None

        # Gọi ENTRY cho trạng thái ban đầu
        self.in_transition = True
        self._execute_state(initial_state, HsmEvent.ENTRY, None)
        self.in_transition = False

        # Kiểm tra nếu ENTRY đã yêu cầu transition deferred
        if self.next is not None:
            next_state = self.next
            self.next = None
            return self.transition(next_state)

        return HsmResult.OK

    def dispatch(self, event: int, data: Any = None) -> HsmResult:
        """Gửi event đến trạng thái hiện tại và lên các parent nếu cần"""
        if self.current is None:
            return HsmResult.INVALID_PARAM

        state = self.current
        evt = event

        while state is not None and evt != HsmEvent.NONE:
            evt = state.handler(self, evt, data)
            state = state.parent

        return HsmResult.OK

    def transition(
        self,
        target: HsmState,
        param: Any = None,
        method: Optional[Callable[['Hsm', Any], None]] = None
    ) -> HsmResult:
        """Chuyển trạng thái đến target (với xử lý exit/entry đúng thứ tự)"""
        if target is None:
            return HsmResult.INVALID_PARAM

        # Nếu đang trong transition → defer transition này
        if self.in_transition:
            self.next = target
            return HsmResult.OK

        if HISTORY:
            self.history = self.current

        lca = self._find_lca(self.current, target)

        # Thu thập exit path (từ current lên đến LCA)
        exit_path = []
        state = self.current
        while state != lca:
            exit_path.append(state)
            state = state.parent

        # Thu thập entry path (từ LCA xuống target)
        entry_path = []
        state = target
        while state != lca:
            entry_path.append(state)
            state = state.parent

        self.in_transition = True

        # Thực hiện EXIT từ dưới lên
        for s in exit_path:
            self._execute_state(s, HsmEvent.EXIT, param)

        # Gọi hook method nếu có (giữa exit và entry)
        if method is not None:
            method(self, param)

        # Thực hiện ENTRY từ trên xuống (reverse order)
        for s in reversed(entry_path):
            self._execute_state(s, HsmEvent.ENTRY, param)

        # Cập nhật trạng thái hiện tại
        self.current = target
        self.depth = self._get_state_depth(target)

        self.in_transition = False

        # Kiểm tra deferred transition trong ENTRY
        if self.next is not None:
            next_state = self.next
            self.next = None
            return self.transition(next_state)

        return HsmResult.OK

    def get_current_state(self) -> Optional[HsmState]:
        return self.current

    def is_in_state(self, state: HsmState) -> bool:
        """Kiểm tra xem HSM đang ở trong state (hoặc con của state)"""
        if state is None:
            return False

        current = self.current
        while current is not None:
            if current == state:
                return True
            current = current.parent
        return False

    if HISTORY:
        def transition_history(self) -> HsmResult:
            """Chuyển về trạng thái trước đó (history)"""
            if self.history is None:
                return self.transition(self.initial)
            return self.transition(self.history)

    # ────────────────────────────────────────────────
    # Private helper methods
    # ────────────────────────────────────────────────

    def _get_state_depth(self, state: HsmState) -> int:
        depth = 0
        current = state
        while current.parent is not None:
            depth += 1
            current = current.parent
        return depth

    def _find_lca(self, s1: HsmState, s2: HsmState) -> Optional[HsmState]:
        if s1 is None or s2 is None:
            return None

        depth1 = self._get_state_depth(s1)
        depth2 = self._get_state_depth(s2)

        # Đưa 2 state về cùng mức
        while depth1 > depth2:
            s1 = s1.parent
            depth1 -= 1
        while depth2 > depth1:
            s2 = s2.parent
            depth2 -= 1

        # Tìm ancestor chung thấp nhất
        while s1 != s2 and s1 is not None and s2 is not None:
            s1 = s1.parent
            s2 = s2.parent

        return s1

    def _execute_state(self, state: HsmState, event: int, data: Any) -> None:
        if state is not None and state.handler is not None:
            state.handler(self, event, data)


