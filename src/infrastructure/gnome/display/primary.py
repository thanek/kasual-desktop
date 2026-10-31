from infrastructure.gnome import helper


class GnomePrimaryDisplay:
    def lend_to_kasual_screen(self) -> None:
        helper.lend_primary_monitor()

    def reclaim(self) -> None:
        helper.reclaim_primary_monitor()
