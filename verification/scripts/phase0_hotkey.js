registerShortcut("SlugcatPet Phase0 Test", "Phase0 test shortcut", "Ctrl+Alt+P", function() {
    callDBus("org.slugcatpet.Phase0", "/Phase0", "org.slugcatpet.Phase0", "Hotkey", 5);
    print("phase0 hotkey fired");
});
print("phase0 hotkey script loaded");
