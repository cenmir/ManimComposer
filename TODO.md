- Tex rotation

- Save project → close → reopen → all scenes/objects/animations restored

- We now have a "gear geometry" module that creates points for 2D gear profiles. I want to be able to add new Design features. Where should we put gear_geometry.py be accessable to  the mainim_composer? I want to be able to import it from the UI, basically adding a new button in the design tab for "Gear":

The properties of the gear would be:
pts = gear_profile_points(N_teeth=N_teeth, module=module, start_tooth=start_tooth)
gear_1 = VMobject()
gear_1.set_points_as_corners(pts)
gear_1.set_stroke(WHITE, width=2)
gear_1.set_fill(fill_color, opacity=1)


Add Mac and Linux installers.


Export to PowerPoint -> exports each scene as a MP¤ video or as a PNG depending on if it is a still image or animation. Then it creates a PowerPoint file with each scene as a slide, and the video or image embedded in the slide.